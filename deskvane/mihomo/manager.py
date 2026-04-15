"""Coordinate Mihomo Party fallback and an embedded mihomo core runtime."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import webbrowser
from typing import Any, Callable

from ..config import MihomoConfig
from ..notifier import Notifier
from .api import MihomoApiClient, MihomoRuntimeState
from .core_manager import MihomoCoreManager, MihomoCoreStatus
from .pac import fetch_remote_pac, generate_pac_script, parse_domain_list
from .pac_server import PacServer

MIHOMO_PARTY_BIN = "mihomo-party"


class MihomoPartyManager:
    """Launch / stop the system-installed Mihomo Party Electron client."""

    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @staticmethod
    def is_installed() -> bool:
        return shutil.which(MIHOMO_PARTY_BIN) is not None

    def start(self) -> bool:
        with self._lock:
            if self.process and self.process.poll() is None:
                return True

            if not self.is_installed():
                self.notifier.show(
                    "Mihomo Party 未安装",
                    "请先安装 mihomo-party：\n"
                    "sudo dpkg -i mihomo-party-linux-*-amd64.deb",
                )
                return False

            try:
                self.process = subprocess.Popen(
                    [MIHOMO_PARTY_BIN, "--no-sandbox"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                threading.Thread(target=self._post_launch_setup, daemon=True).start()
                return True
            except Exception as exc:
                self.notifier.show("启动 Mihomo Party 失败", str(exc))
                return False

    def _post_launch_setup(self) -> None:
        time.sleep(2)
        self._try_hide_tray_icon()

    def stop(self) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
            self.process = None

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def show_window(self) -> None:
        if not self.is_running():
            self.start()
            return
        try:
            subprocess.Popen(
                [MIHOMO_PARTY_BIN, "--no-sandbox"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    @staticmethod
    def _try_hide_tray_icon() -> None:
        def _hide() -> None:
            time.sleep(4)
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--classname", "mihomo-party"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0 or not result.stdout.strip():
                    return
                for wid in result.stdout.strip().split("\n"):
                    wid = wid.strip()
                    if not wid:
                        continue
                    geo = subprocess.run(
                        ["xdotool", "getwindowgeometry", wid],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if geo.returncode != 0 or "Geometry:" not in geo.stdout:
                        continue
                    size_str = geo.stdout.split("Geometry:")[1].strip().split()[0]
                    try:
                        w, h = size_str.split("x")
                        if int(w) <= 64 and int(h) <= 64:
                            subprocess.run(
                                ["xdotool", "windowunmap", wid],
                                timeout=5,
                            )
                    except (ValueError, IndexError):
                        pass
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        threading.Thread(target=_hide, daemon=True).start()


class MihomoManager:
    """Route Mihomo actions to the configured backend."""

    def __init__(
        self,
        notifier: Notifier,
        config_provider: Callable[[], MihomoConfig],
    ) -> None:
        self.notifier = notifier
        self._config_provider = config_provider
        self.party = MihomoPartyManager(notifier)
        self.core = MihomoCoreManager(notifier, config_provider)
        self._pac_server: PacServer | None = None

    @property
    def backend(self) -> str:
        backend = getattr(self._config_provider(), "backend", "party")
        return backend if backend in {"party", "core"} else "party"

    @property
    def display_name(self) -> str:
        return "Mihomo Core" if self.backend == "core" else "Mihomo Party"

    def _active(self):
        return self.core if self.backend == "core" else self.party

    def _inactive(self):
        return self.party if self.backend == "core" else self.core

    def is_installed(self) -> bool:
        return self._active().is_installed()

    def is_running(self) -> bool:
        return self._active().is_running()

    def start(self) -> bool:
        self._inactive().stop()
        ok = self._active().start()
        if ok:
            self._start_pac_if_needed()
        return ok

    def stop(self) -> None:
        self._active().stop()
        self._stop_pac()

    def stop_all(self) -> None:
        self.party.stop()
        self.core.stop()
        self._stop_pac()

    def show_window(self) -> None:
        if self.backend == "core":
            self.open_controller()
            return
        self.party.show_window()

    def open_controller(self) -> None:
        status = self.core.get_status()
        if not status.api_ready:
            self.notifier.show("Mihomo Core 未就绪", "控制 API 尚未就绪，请先启动核心并确认配置有效。")
            return
        try:
            cfg = self._config_provider()
            has_external_ui = bool(
                cfg.external_ui.strip() or cfg.external_ui_name.strip() or cfg.external_ui_url.strip()
            )
            target = f"{status.controller}/ui" if has_external_ui else status.controller
            webbrowser.open(target)
        except Exception as exc:
            self.notifier.show("打开控制地址失败", str(exc))

    def get_core_status(self) -> MihomoCoreStatus:
        return self.core.get_status()

    def reload_config(self) -> None:
        try:
            self.core.ensure_runtime_config()
        except Exception as exc:
            self.notifier.show("Mihomo 配置同步失败", str(exc))

    def reload_core_config(self) -> bool:
        return self.core.reload_config()

    def refresh_tun_bypass_connections(self, processes: str) -> int:
        return self.core.refresh_tun_bypass_connections(processes)

    def save_subscription_provider(
        self,
        proxies: list[dict[str, Any]],
        source: str,
    ) -> str:
        path = self.core.write_subscription_provider(proxies, source)
        return str(path)

    def _api_client(self) -> MihomoApiClient:
        cfg = self._config_provider()
        return MihomoApiClient(
            controller=cfg.external_controller,
            secret=cfg.secret,
        )

    def get_runtime_state(self) -> MihomoRuntimeState:
        return self._api_client().get_runtime_state()

    def switch_mode(self, mode: str) -> bool:
        return self.core.switch_mode(mode)

    def switch_tun(self, enabled: bool) -> bool:
        return self.core.switch_tun(enabled)

    def switch_proxy(self, group_name: str, proxy_name: str) -> bool:
        return self._api_client().switch_proxy(group_name, proxy_name)

    def test_proxy_delay(
        self,
        proxy_name: str,
        test_url: str,
        timeout_ms: int = 5000,
    ) -> int | None:
        return self._api_client().test_proxy_delay(
            proxy_name,
            test_url=test_url,
            timeout_ms=timeout_ms,
        )

    # ---------------------------------------------------------------
    # PAC server management
    # ---------------------------------------------------------------

    def _build_pac_generator(self):
        """Return a callable that generates the current PAC script."""
        # Resolve proxy port once at build time; restart_pac rebuilds the generator.
        proxy_port = 7890
        try:
            runtime = self.get_runtime_state()
            if runtime.mixed_port:
                proxy_port = runtime.mixed_port
            elif runtime.port:
                proxy_port = runtime.port
        except Exception:
            pass

        # If API wasn't ready, read port from config file directly.
        if proxy_port == 7890:
            try:
                import yaml
                from pathlib import Path
                cfg = self._config_provider()
                config_path = Path(cfg.core_home_dir).expanduser() / "config.yaml"
                if config_path.exists():
                    with open(config_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    proxy_port = data.get("mixed-port") or data.get("port") or 7890
            except Exception:
                pass

        def generator() -> str:
            cfg = self._config_provider()

            # Remote PAC mode: fetch external PAC and rewrite proxy address
            remote_url = getattr(cfg, "pac_remote_url", "") or ""
            if remote_url.strip():
                from pathlib import Path as _Path
                cache_dir = _Path(cfg.core_home_dir) / "pac_cache"
                return fetch_remote_pac(
                    url=remote_url.strip(),
                    proxy_port=proxy_port,
                    cache_dir=cache_dir,
                )

            # Local domain-list mode
            return generate_pac_script(
                proxy_port=proxy_port,
                proxy_domains=parse_domain_list(cfg.pac_proxy_domains),
                direct_domains=parse_domain_list(cfg.pac_direct_domains),
                default_action=cfg.pac_default_action,
            )
        return generator

    def _start_pac_if_needed(self) -> bool:
        cfg = self._config_provider()
        if not cfg.pac_enabled:
            self._stop_pac()
            return True
        if self._pac_server is not None and self._pac_server.is_running():
            if self._pac_server.port == cfg.pac_port:
                return True
            return self._pac_server.restart(cfg.pac_port)
        self._pac_server = PacServer(cfg.pac_port, self._build_pac_generator())
        ok = self._pac_server.start()
        if not ok:
            self.notifier.show(
                "PAC 服务启动失败",
                f"端口 {cfg.pac_port} 可能被占用，请尝试修改 PAC 端口。",
            )
        return ok

    def _stop_pac(self) -> None:
        if self._pac_server is not None:
            self._pac_server.stop()
            self._pac_server = None

    @property
    def pac_url(self) -> str:
        cfg = self._config_provider()
        return f"http://127.0.0.1:{cfg.pac_port}/pac"

    def is_pac_running(self) -> bool:
        return self._pac_server is not None and self._pac_server.is_running()

    def set_pac_enabled(self, enabled: bool) -> None:
        """Start or stop the PAC server based on the desired state."""
        if enabled:
            self._start_pac_if_needed()
        else:
            self._stop_pac()

    def restart_pac(self) -> bool:
        """Restart the PAC server with current config."""
        self._stop_pac()
        cfg = self._config_provider()
        if not cfg.pac_enabled:
            return False
        self._pac_server = PacServer(cfg.pac_port, self._build_pac_generator())
        return self._pac_server.start()
