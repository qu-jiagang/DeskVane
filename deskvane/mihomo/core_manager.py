"""Manage a local mihomo core process and keep its runtime config aligned."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TextIO

import yaml

from ..config import MihomoConfig
from ..notifier import Notifier
from .api import MihomoApiClient
from .pac import (
    extract_domains_from_pac_js,
    parse_domain_list,
    sync_pac_rules,
)


@dataclass(slots=True)
class MihomoCoreStatus:
    installed: bool
    running: bool
    api_ready: bool
    pid: int | None
    binary: str
    home_dir: str
    config_path: str
    controller: str
    last_error: str
    config_exists: bool
    config_error: str
    logs_dir: str
    stdout_log_path: str
    stderr_log_path: str
    provider_path: str
    provider_exists: bool
    subscription_source: str
    subscription_updated_at: str
    subscription_proxy_count: int


_MANAGED_PROVIDER_NAME = "deskvane-subscription"
_MANAGED_PROVIDER_FILE = "providers/deskvane-subscription.yaml"
_MANAGED_META_FILE = "providers/deskvane-subscription.meta.yaml"
_MANAGED_PROXY_GROUP = "DESKVANE-PROXY"
_MANAGED_AUTO_GROUP = "DESKVANE-AUTO"
_HEALTHCHECK_URL = "https://www.gstatic.com/generate_204"


class MihomoCoreManager:
    """Launch and manage a standalone mihomo core process."""

    def __init__(
        self,
        notifier: Notifier,
        config_provider: Callable[[], MihomoConfig],
    ) -> None:
        self.notifier = notifier
        self._config_provider = config_provider
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stdout_handle: TextIO | None = None
        self._stderr_handle: TextIO | None = None
        self._last_error = ""

    def _cfg(self) -> MihomoConfig:
        return self._config_provider()

    def _binary(self) -> str:
        raw = self._cfg().core_binary.strip() or "mihomo"
        return os.path.expanduser(raw)

    def _resolved_binary(self) -> Path | None:
        binary = self._binary()
        if "/" in binary:
            path = Path(binary)
            return path if path.exists() else None
        resolved = shutil.which(binary)
        return Path(resolved) if resolved else None

    def _home_dir(self) -> Path:
        raw = self._cfg().core_home_dir.strip() or "~/.config/deskvane/mihomo"
        return Path(os.path.expanduser(raw))

    def _config_path(self) -> Path:
        return self._home_dir() / "config.yaml"

    def _logs_dir(self) -> Path:
        return self._home_dir() / "logs"

    def _stdout_log_path(self) -> Path:
        return self._logs_dir() / "core.stdout.log"

    def _stderr_log_path(self) -> Path:
        return self._logs_dir() / "core.stderr.log"

    def _providers_dir(self) -> Path:
        return self._home_dir() / "providers"

    def _provider_path(self) -> Path:
        return self._home_dir() / _MANAGED_PROVIDER_FILE

    def _provider_meta_path(self) -> Path:
        return self._home_dir() / _MANAGED_META_FILE

    def _api_client(self) -> MihomoApiClient:
        cfg = self._cfg()
        return MihomoApiClient(
            controller=cfg.external_controller,
            secret=cfg.secret,
        )

    def controller_url(self) -> str:
        return self._api_client().base_url

    def is_installed(self) -> bool:
        binary = self._binary()
        if "/" in binary:
            return Path(binary).exists()
        return shutil.which(binary) is not None

    def is_running(self) -> bool:
        return self.get_status().running

    def write_subscription_provider(
        self,
        proxies: list[dict[str, Any]],
        source: str,
    ) -> Path:
        if not proxies:
            raise ValueError("订阅内容里没有可写入的节点。")

        provider_dir = self._providers_dir()
        provider_dir.mkdir(parents=True, exist_ok=True)
        provider_path = self._provider_path()
        provider_data = {"proxies": proxies}
        provider_path.write_text(
            yaml.dump(provider_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        meta = {
            "source": source.strip(),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "proxy_count": len(proxies),
        }
        self._provider_meta_path().write_text(
            yaml.dump(meta, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        self.ensure_runtime_config()
        self._last_error = ""
        return provider_path

    def ensure_runtime_config(self) -> Path:
        cfg = self._cfg()
        home_dir = self._home_dir()
        home_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._config_path()

        data, load_error = self._load_yaml_mapping(config_path)
        if load_error:
            raise ValueError(f"主配置文件无法解析：{load_error}")

        controller = cfg.external_controller.strip() or "127.0.0.1:9090"
        secret = cfg.secret
        external_ui = cfg.external_ui.strip()
        external_ui_name = cfg.external_ui_name.strip()
        external_ui_url = cfg.external_ui_url.strip()
        changed = False

        if data.get("external-controller") != controller:
            data["external-controller"] = controller
            changed = True
        if data.get("secret", "") != secret:
            data["secret"] = secret
            changed = True
        if external_ui and data.get("external-ui", "") != external_ui:
            data["external-ui"] = external_ui
            changed = True
        if external_ui_name and data.get("external-ui-name", "") != external_ui_name:
            data["external-ui-name"] = external_ui_name
            changed = True
        if external_ui_url and data.get("external-ui-url", "") != external_ui_url:
            data["external-ui-url"] = external_ui_url
            changed = True
        if "mixed-port" not in data and "port" not in data and "socks-port" not in data:
            data["mixed-port"] = 7890
            changed = True
        if "mode" not in data:
            data["mode"] = "rule"
            changed = True
        if "log-level" not in data:
            data["log-level"] = "info"
            changed = True

        changed = self._ensure_tun_config(data, cfg.tun_enabled, cfg.tun_direct_processes) or changed
        changed = self._ensure_managed_subscription_support(data) or changed
        changed = self._sync_inline_proxies_from_provider(data) or changed
        changed = self._ensure_pac_rules(data, cfg) or changed

        if changed or not config_path.exists():
            config_path.write_text(
                yaml.dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        return config_path

    def start(self) -> bool:
        if self.get_status().running:
            return True
        with self._lock:
            if self.process and self.process.poll() is None:
                return True

            if not self.is_installed():
                self._last_error = f"未找到 mihomo core：{self._binary()}"
                self.notifier.show("Mihomo Core 未安装", self._last_error)
                return False

            try:
                cfg = self._cfg()
                self.ensure_runtime_config()
                conflict_error = self._startup_preflight_error()
                if conflict_error:
                    self._last_error = conflict_error
                    self.notifier.show("启动 Mihomo Core 失败", conflict_error)
                    return False
                logs_dir = self._logs_dir()
                logs_dir.mkdir(parents=True, exist_ok=True)
                self._stdout_handle = open(self._stdout_log_path(), "a", encoding="utf-8")
                self._stderr_handle = open(self._stderr_log_path(), "a", encoding="utf-8")
                self.process = subprocess.Popen(
                    [self._binary(), "-d", str(self._home_dir())],
                    stdout=self._stdout_handle,
                    stderr=self._stderr_handle,
                    start_new_session=True,
                )
                self._last_error = ""
                early_exit_error = self._wait_for_early_exit()
                if early_exit_error:
                    self._last_error = early_exit_error
                    self._close_log_handles()
                    self.process = None
                    self.notifier.show("启动 Mihomo Core 失败", early_exit_error)
                    return False
                threading.Thread(
                    target=self._probe_api_readiness,
                    args=(cfg.startup_timeout_s,),
                    daemon=True,
                ).start()
                return True
            except Exception as exc:
                self._last_error = str(exc)
                self._close_log_handles()
                self.process = None
                self.notifier.show("启动 Mihomo Core 失败", str(exc))
                return False

    def stop(self) -> None:
        external_pid = None
        with self._lock:
            process = self.process
        if process is None or process.poll() is not None:
            external_pid = self._find_external_process_pid()

        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
            elif external_pid:
                self._terminate_external_pid(external_pid)
            self.process = None
            self._close_log_handles()

    def reload_config(self) -> bool:
        try:
            self.ensure_runtime_config()
        except Exception as exc:
            self._last_error = str(exc)
            self.notifier.show("Mihomo 配置重载失败", str(exc))
            return False
        if not self.is_running():
            return False
        ok = self._api_client().reload_config()
        if ok:
            self._last_error = ""
            return True
        self._last_error = "Mihomo Core 已运行，但控制 API 配置重载失败。"
        return False

    def refresh_tun_bypass_connections(self, direct_processes: str) -> int:
        process_names = _expand_process_bypass_names(direct_processes)
        domain_suffixes = _expand_process_bypass_domain_suffixes(process_names)
        if not process_names and not domain_suffixes:
            return 0

        closed = 0
        for connection in self._api_client().get_connections():
            if not self._connection_matches_bypass_targets(connection, process_names, domain_suffixes):
                continue
            connection_id = str(connection.get("id") or "").strip()
            if not connection_id:
                continue
            if self._api_client().close_connection(connection_id):
                closed += 1
        return closed

    def switch_mode(self, mode: str) -> bool:
        normalized = mode.strip().lower()
        if normalized not in {"rule", "global", "direct"}:
            self._last_error = f"不支持的 Mihomo 模式：{mode}"
            return False

        ok = self._api_client().switch_mode(normalized)
        if not ok:
            self._last_error = "控制 API 调用失败，请确认 Core 已启动且控制地址可访问。"
            return False

        self._last_error = ""
        try:
            self._persist_runtime_mode(normalized)
        except Exception as exc:
            self.notifier.show("Mihomo 模式持久化失败", str(exc))
        return True

    def switch_tun(self, enabled: bool) -> bool:
        log_offset = self._log_size(self._stdout_log_path())
        if enabled:
            tun_error = self._tun_preflight_error()
            if tun_error:
                self._last_error = tun_error
                return False

        ok = self._api_client().switch_tun(enabled)
        if not ok:
            self._last_error = "控制 API 调用失败，请确认 Core 已启动且控制地址可访问。"
            return False

        if not enabled:
            self._last_error = ""
            return True

        deadline = time.monotonic() + 1.5
        saw_enabled = False
        while time.monotonic() < deadline:
            runtime = self._api_client().get_runtime_state()
            if runtime.api_ready and runtime.tun_enabled:
                saw_enabled = True

            runtime_error = self._read_tun_error_since(log_offset)
            if runtime_error:
                self._last_error = f"TUN 启动失败：{runtime_error}"
                return False
            time.sleep(0.15)

        if saw_enabled:
            self._last_error = ""
            return True

        self._last_error = "TUN 状态未生效，请检查 mihomo 权限和日志。"
        return False

    def get_status(self) -> MihomoCoreStatus:
        with self._lock:
            process = self.process
            child_running = process is not None and process.poll() is None
            pid = process.pid if child_running else None

        _, config_error = self._load_yaml_mapping(self._config_path())
        meta = self._load_subscription_meta()
        subscription_proxy_count = _to_int(meta.get("proxy_count")) or 0
        api_ready = self._api_client().is_healthy()
        if api_ready and pid is None:
            pid = self._find_external_process_pid()
        running = child_running or api_ready
        if api_ready and self._last_error.startswith("控制 API 在 "):
            self._last_error = ""
        return MihomoCoreStatus(
            installed=self.is_installed(),
            running=running,
            api_ready=api_ready,
            pid=pid,
            binary=self._binary(),
            home_dir=str(self._home_dir()),
            config_path=str(self._config_path()),
            controller=self.controller_url(),
            last_error=self._last_error,
            config_exists=self._config_path().exists(),
            config_error=config_error,
            logs_dir=str(self._logs_dir()),
            stdout_log_path=str(self._stdout_log_path()),
            stderr_log_path=str(self._stderr_log_path()),
            provider_path=str(self._provider_path()),
            provider_exists=self._provider_path().exists(),
            subscription_source=str(meta.get("source", "")),
            subscription_updated_at=str(meta.get("updated_at", "")),
            subscription_proxy_count=subscription_proxy_count,
        )

    def _probe_api_readiness(self, timeout_s: int) -> None:
        effective_timeout = max(timeout_s, 20)
        deadline = time.monotonic() + effective_timeout
        while time.monotonic() < deadline:
            with self._lock:
                process = self.process
            if process is None or process.poll() is not None:
                return
            if self._api_client().is_healthy():
                self._last_error = ""
                return
            time.sleep(0.25)
        startup_hint = self._startup_hint()
        if startup_hint:
            self._last_error = f"控制 API 在 {effective_timeout} 秒内未就绪，{startup_hint}"
        else:
            self._last_error = f"控制 API 在 {effective_timeout} 秒内未就绪，请检查配置和日志。"
        self.notifier.show("Mihomo Core 启动超时", self._last_error)

    def _wait_for_early_exit(self, window_s: float = 0.4) -> str:
        process = self.process
        if process is None:
            return ""
        deadline = time.monotonic() + window_s
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                return self._startup_exit_error(exit_code)
            time.sleep(0.05)
        return ""

    def _startup_exit_error(self, exit_code: int) -> str:
        stderr_tail = self._recent_log_text(self._stderr_log_path(), max_bytes=2048).strip()
        stdout_tail = self._recent_log_text(self._stdout_log_path(), max_bytes=2048).strip()
        detail = stderr_tail or stdout_tail
        message = f"mihomo core 启动后立即退出，exit code {exit_code}。"
        if detail:
            message += f" 最近日志：{detail.splitlines()[-1].strip()}"
        return message

    def _find_external_process_pid(self) -> int | None:
        home_dir = str(self._home_dir())
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_text, command = parts
            pid = _to_int(pid_text)
            if not pid:
                continue
            if f" -d {home_dir}" not in command and not command.endswith(f"-d {home_dir}"):
                continue
            try:
                argv = shlex.split(command)
            except ValueError:
                argv = command.split()
            if not argv:
                continue
            if "mihomo" not in Path(argv[0]).name.lower():
                continue
            return pid
        return None

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _terminate_external_pid(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not self._pid_exists(pid):
                return
            time.sleep(0.1)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def _close_log_handles(self) -> None:
        for handle_name in ("_stdout_handle", "_stderr_handle"):
            handle = getattr(self, handle_name)
            if handle is None:
                continue
            try:
                handle.close()
            except Exception:
                pass
            setattr(self, handle_name, None)

    def _load_yaml_mapping(self, path: Path) -> tuple[dict[str, Any], str]:
        if not path.exists():
            return {}, ""
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            return {}, str(exc)
        if loaded is None:
            return {}, ""
        if not isinstance(loaded, dict):
            return {}, "根节点必须是 YAML 映射。"
        return dict(loaded), ""

    def _persist_runtime_mode(self, mode: str) -> None:
        config_path = self.ensure_runtime_config()
        data, error = self._load_yaml_mapping(config_path)
        if error:
            raise RuntimeError(error)
        if data.get("mode") == mode:
            return
        data["mode"] = mode
        config_path.write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _load_subscription_meta(self) -> dict[str, Any]:
        meta, _error = self._load_yaml_mapping(self._provider_meta_path())
        return meta

    def _startup_preflight_error(self) -> str:
        data, load_error = self._load_yaml_mapping(self._config_path())
        if load_error:
            return f"主配置文件无法解析：{load_error}"

        conflicts: list[str] = []
        for label, host, port, proto in self._startup_bind_targets(data):
            if not self._is_bind_available(host, port, proto):
                host_label = host or "0.0.0.0"
                conflicts.append(f"{label} {proto.upper()} {host_label}:{port}")

        if not conflicts:
            return ""

        detail = "端口已被占用：" + "，".join(conflicts) + "。"
        if self._party_sidecar_running() and any(":7890" in item or ":7891" in item for item in conflicts):
            detail += " 当前检测到 mihomo-party sidecar 仍在运行，优先检查它是否占用了代理端口。"
        return detail

    def _startup_bind_targets(self, data: dict[str, Any]) -> list[tuple[str, str, int, str]]:
        targets: list[tuple[str, str, int, str]] = []

        controller = str(data.get("external-controller") or self._cfg().external_controller or "").strip()
        parsed_controller = self._parse_host_port(controller)
        if parsed_controller is not None:
            host, port = parsed_controller
            targets.append(("控制 API", host, port, "tcp"))

        allow_lan = bool(data.get("allow-lan"))
        bind_host = "127.0.0.1"
        if allow_lan:
            bind_host = str(data.get("bind-address") or "*").strip() or "*"

        for key, label in (
            ("mixed-port", "Mixed 代理"),
            ("port", "HTTP 代理"),
            ("socks-port", "SOCKS 代理"),
        ):
            port = _to_int(data.get(key))
            if port:
                targets.append((label, bind_host, port, "tcp"))

        dns = data.get("dns")
        if isinstance(dns, dict) and dns.get("enable"):
            parsed_dns = self._parse_host_port(str(dns.get("listen") or "").strip(), default_port=1053)
            if parsed_dns is not None:
                host, port = parsed_dns
                targets.append(("DNS", host, port, "tcp"))
                targets.append(("DNS", host, port, "udp"))

        deduped: list[tuple[str, str, int, str]] = []
        seen: set[tuple[str, str, int, str]] = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            deduped.append(target)
        return deduped

    @staticmethod
    def _parse_host_port(raw: str, default_port: int | None = None) -> tuple[str, int] | None:
        value = raw.strip()
        if not value:
            if default_port is None:
                return None
            return ("127.0.0.1", default_port)
        if "://" in value:
            value = value.split("://", 1)[1]
        if value.startswith(":"):
            if default_port is not None:
                return ("0.0.0.0", _to_int(value[1:]) or default_port)
            parsed_port = _to_int(value[1:])
            return ("0.0.0.0", parsed_port) if parsed_port else None
        if value.count(":") == 1:
            host, port_text = value.rsplit(":", 1)
            parsed_port = _to_int(port_text)
            if parsed_port:
                return (host or "127.0.0.1", parsed_port)
        if default_port is not None:
            return (value, default_port)
        return None

    @staticmethod
    def _normalize_bind_host(host: str) -> str:
        normalized = host.strip() or "127.0.0.1"
        if normalized in {"*", "::", "[::]"}:
            return "0.0.0.0"
        return normalized

    def _is_bind_available(self, host: str, port: int, proto: str) -> bool:
        sock_type = socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM
        bind_host = self._normalize_bind_host(host)
        family = socket.AF_INET6 if ":" in bind_host and bind_host != "0.0.0.0" else socket.AF_INET
        try:
            with socket.socket(family, sock_type) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((bind_host, port))
            return True
        except OSError:
            return False

    @staticmethod
    def _party_sidecar_running() -> bool:
        try:
            result = subprocess.run(
                ["ps", "-ef"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except Exception:
            return False
        return "/opt/mihomo-party/resources/sidecar/mihomo" in result.stdout

    def _startup_hint(self) -> str:
        recent_log = self._recent_log_text(self._stdout_log_path(), max_bytes=8192).lower()
        if "mmdb invalid" in recent_log or "can't find mmdb" in recent_log:
            return "首次启动可能正在下载 geodata/MMDB，可稍等十几秒后再看状态。"
        return ""

    @staticmethod
    def _connection_matches_bypass_targets(
        connection: dict[str, Any],
        process_names: list[str],
        domain_suffixes: list[str],
    ) -> bool:
        metadata = connection.get("metadata")
        if not isinstance(metadata, dict):
            return False

        process = str(metadata.get("process") or "").strip()
        if process:
            normalized_process = process.casefold()
            if any(normalized_process == name.casefold() for name in process_names):
                return True

        host = str(metadata.get("host") or "").strip().rstrip(".")
        if not host:
            return False

        normalized_host = host.casefold()
        for domain in domain_suffixes:
            normalized_domain = domain.strip().casefold().lstrip(".")
            if not normalized_domain:
                continue
            if normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}"):
                return True
        return False

    def _tun_preflight_error(self) -> str:
        if os.name != "posix":
            return ""
        if not Path("/dev/net/tun").exists():
            return "系统缺少 /dev/net/tun，当前环境不支持 TUN。"
        if os.geteuid() == 0:
            return ""

        binary = self._resolved_binary()
        if binary is None:
            return f"未找到 mihomo core：{self._binary()}"

        getcap = shutil.which("getcap")
        if not getcap:
            return ""

        try:
            result = subprocess.run(
                [getcap, str(binary)],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except Exception:
            return ""

        capability_text = f"{result.stdout}\n{result.stderr}".lower()
        if "cap_net_admin" in capability_text:
            return ""
        return (
            f"TUN 需要 CAP_NET_ADMIN 权限，当前 mihomo 二进制没有该能力：{binary}。"
        )

    @staticmethod
    def _log_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _extract_log_message(line: str) -> str:
        match = re.search(r'msg="([^"]+)"', line)
        if match:
            return match.group(1).strip()
        return line.strip()

    def _read_tun_error_since(self, offset: int) -> str:
        path = self._stdout_log_path()
        if not path.exists():
            return ""
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                if offset > 0:
                    handle.seek(offset)
                chunk = handle.read()
        except OSError:
            return ""

        for line in reversed(chunk.splitlines()):
            lower = line.lower()
            if "tun" not in lower:
                continue
            if "error" in lower or "not permitted" in lower or "permission denied" in lower:
                return self._extract_log_message(line)
        return ""

    @staticmethod
    def _recent_log_text(path: Path, max_bytes: int = 4096) -> str:
        if not path.exists():
            return ""
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes))
                return handle.read().decode("utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _ensure_tun_config(
        data: dict[str, Any],
        enabled: bool,
        direct_processes: str = "",
    ) -> bool:
        """Inject or update TUN and DNS blocks based on the desired state.

        If the user already has a ``tun`` section we only touch ``enable``.
        When TUN is first enabled and no ``dns`` block exists we inject
        sensible defaults so that fake-ip resolution works out of the box.
        When *direct_processes* is non-empty, ``PROCESS-NAME,...,DIRECT``
        rules are managed at the top of the ``rules`` list. Some apps also
        ship privileged helper processes whose traffic exposes only ``uid``
        but no process name in Mihomo. For those known apps we also inject
        narrow ``DOMAIN-SUFFIX,...,DIRECT`` fallback rules.
        """
        changed = False

        tun = data.get("tun")
        if not isinstance(tun, dict):
            if not enabled:
                # Still need to clean up stale bypass rules.
                changed = _sync_process_bypass_rules(data, []) or changed
                return changed
            tun = {}
            data["tun"] = tun
            changed = True

        if tun.get("enable") != enabled:
            tun["enable"] = enabled
            changed = True

        # Parse desired bypass process names.
        desired = _expand_process_bypass_names(direct_processes) if enabled else []
        changed = _sync_process_bypass_rules(data, desired) or changed
        if desired and "find-process-mode" not in data:
            # Process-name rules are more reliable on Linux when Mihomo is told
            # to always resolve the owning process instead of leaving it to the
            # platform default.
            data["find-process-mode"] = "always"
            changed = True

        if enabled:
            # Provide sensible defaults only when keys are missing.
            _tun_defaults: dict[str, Any] = {
                "stack": "mixed",
                "auto-route": True,
                "auto-detect-interface": True,
            }
            for key, value in _tun_defaults.items():
                if key not in tun:
                    tun[key] = value
                    changed = True

            # DNS must be enabled for TUN fake-ip to work properly.
            dns = data.get("dns")
            if not isinstance(dns, dict):
                dns = {}
                data["dns"] = dns
                changed = True
            if not dns.get("enable"):
                dns["enable"] = True
                changed = True
            _dns_defaults: dict[str, Any] = {
                "default-nameserver": [
                    "223.5.5.5",
                    "1.1.1.1",
                ],
                "listen": ":1053",
                "enhanced-mode": "fake-ip",
                "fake-ip-range": "198.18.0.1/16",
                "nameserver": [
                    "https://dns.alidns.com/dns-query",
                    "https://doh.pub/dns-query",
                ],
                "fallback": [
                    "https://1.0.0.1/dns-query",
                    "https://dns.google/dns-query",
                ],
            }
            for key, value in _dns_defaults.items():
                if key not in dns:
                    dns[key] = value
                    changed = True
        else:
            managed_dns = data.get("dns")
            if isinstance(managed_dns, dict):
                managed_keys = {
                    "enable",
                    "default-nameserver",
                    "listen",
                    "enhanced-mode",
                    "fake-ip-range",
                    "nameserver",
                    "fallback",
                }
                if (
                    set(managed_dns.keys()).issubset(managed_keys)
                    and managed_dns.get("enable") is True
                    and managed_dns.get("default-nameserver") == ["223.5.5.5", "1.1.1.1"]
                    and managed_dns.get("listen") == ":1053"
                    and managed_dns.get("enhanced-mode") == "fake-ip"
                    and managed_dns.get("fake-ip-range") == "198.18.0.1/16"
                ):
                    data.pop("dns", None)
                    changed = True

        return changed

    def _ensure_managed_subscription_support(self, data: dict[str, Any]) -> bool:
        provider_path = self._provider_path()
        if not provider_path.exists():
            return False

        changed = False
        providers = data.get("proxy-providers")
        if not isinstance(providers, dict):
            providers = {}
            data["proxy-providers"] = providers
            changed = True

        provider_payload = {
            "type": "file",
            "path": _MANAGED_PROVIDER_FILE,
            "health-check": {
                "enable": True,
                "url": _HEALTHCHECK_URL,
                "interval": 300,
            },
        }
        if providers.get(_MANAGED_PROVIDER_NAME) != provider_payload:
            providers[_MANAGED_PROVIDER_NAME] = provider_payload
            changed = True

        groups = data.get("proxy-groups")
        if not isinstance(groups, list):
            groups = []
            data["proxy-groups"] = groups
            changed = True

        managed_groups = [
            {
                "name": _MANAGED_AUTO_GROUP,
                "type": "url-test",
                "use": [_MANAGED_PROVIDER_NAME],
                "url": _HEALTHCHECK_URL,
                "interval": 300,
            },
            {
                "name": _MANAGED_PROXY_GROUP,
                "type": "select",
                "use": [_MANAGED_PROVIDER_NAME],
                "proxies": [_MANAGED_AUTO_GROUP, "DIRECT"],
            },
        ]
        for group in managed_groups:
            if self._upsert_named_entry(groups, group["name"], group):
                changed = True

        rules = data.get("rules")
        if not isinstance(rules, list) or not rules:
            data["rules"] = [
                "DOMAIN-SUFFIX,local,DIRECT",
                "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
                "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
                "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
                "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
                f"MATCH,{_MANAGED_PROXY_GROUP}",
            ]
            changed = True

        return changed

    def _sync_inline_proxies_from_provider(self, data: dict[str, Any]) -> bool:
        """Refresh same-name inline proxies from the managed provider.

        Some users keep handwritten ``PROXY`` / ``Auto`` groups that still point
        at top-level ``proxies`` entries by node name. In that mixed mode, only
        writing the managed provider would leave those inline entries stale.
        Update same-name inline proxies so subscription refreshes actually affect
        the user's active routing path without rewriting unrelated groups/rules.
        """
        proxies = data.get("proxies")
        if not isinstance(proxies, list) or not proxies:
            return False

        provider_data, _error = self._load_yaml_mapping(self._provider_path())
        provider_proxies = provider_data.get("proxies")
        if not isinstance(provider_proxies, list) or not provider_proxies:
            return False

        index_by_name: dict[str, int] = {}
        for index, payload in enumerate(proxies):
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name", "")).strip()
            if not name:
                continue
            index_by_name[name] = index

        changed = False
        for payload in provider_proxies:
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name", "")).strip()
            if not name or name not in index_by_name:
                continue
            proxy_index = index_by_name[name]
            inline_payload = proxies[proxy_index]
            if inline_payload == payload:
                continue
            proxies[proxy_index] = dict(payload)
            changed = True
        return changed

    @staticmethod
    def _ensure_pac_rules(data: dict[str, Any], cfg: MihomoConfig) -> bool:
        """Sync PAC domain rules into the Mihomo config rules list.

        When PAC is enabled, ``pac_proxy_domains`` become
        ``DOMAIN-SUFFIX,...,<proxy_group>`` rules and ``pac_direct_domains``
        become ``DOMAIN-SUFFIX,...,DIRECT`` rules.  The rules are inserted
        before the final ``MATCH`` catch-all so they participate in TUN-mode
        routing.

        If ``pac_remote_url`` is set, domains are extracted from a previously
        cached copy of the remote PAC file (saved to disk by the PAC server).
        No network I/O is performed here — this method runs during config
        generation which happens *before* Mihomo starts.
        """
        remote_url = getattr(cfg, "pac_remote_url", "") or ""
        if remote_url.strip() and cfg.pac_enabled:
            # Try to read from disk cache only — no network requests.
            proxy_domains: list[str] = []
            cache_dir = Path(cfg.core_home_dir) / "pac_cache"
            import re as _re
            safe_name = _re.sub(r"[^\w]", "_", remote_url.strip())[:120] + ".pac"
            cache_file = cache_dir / safe_name
            if cache_file.exists():
                try:
                    cached_pac = cache_file.read_text(encoding="utf-8")
                    proxy_domains = extract_domains_from_pac_js(cached_pac)
                except Exception:
                    pass
            direct_domains: list[str] = []
        else:
            proxy_domains = parse_domain_list(cfg.pac_proxy_domains)
            direct_domains = parse_domain_list(cfg.pac_direct_domains)
        proxy_group = _MANAGED_PROXY_GROUP
        return sync_pac_rules(
            data,
            proxy_domains=proxy_domains,
            direct_domains=direct_domains,
            proxy_group=proxy_group,
            default_action=getattr(cfg, "pac_default_action", "PROXY"),
            enabled=cfg.pac_enabled,
        )

    @staticmethod
    def _upsert_named_entry(
        items: list[Any],
        name: str,
        payload: dict[str, Any],
    ) -> bool:
        for index, item in enumerate(items):
            if not isinstance(item, dict) or item.get("name") != name:
                continue
            if item == payload:
                return False
            items[index] = payload
            return True
        items.append(payload)
        return True


_BYPASS_RULE_PREFIX = "PROCESS-NAME,"
_LEGACY_BYPASS_WILDCARD_RULE_PREFIX = "PROCESS-NAME-WILDCARD,"
_BYPASS_RULE_SUFFIX = ",DIRECT"
_DOMAIN_BYPASS_RULE_PREFIX = "DOMAIN-SUFFIX,"
_KNOWN_PROCESS_BYPASS_DOMAIN_SUFFIXES = {
    "todesk": ["todesk.com"],
    "todesk_service": ["todesk.com"],
}
_KNOWN_BYPASS_DOMAIN_RULES = {
    f"{_DOMAIN_BYPASS_RULE_PREFIX}{domain}{_BYPASS_RULE_SUFFIX}"
    for domains in _KNOWN_PROCESS_BYPASS_DOMAIN_SUFFIXES.values()
    for domain in domains
}


def _is_managed_bypass_rule(rule: str) -> bool:
    """Return True if *rule* looks like a DeskVane-managed process bypass rule."""
    return (
        isinstance(rule, str)
        and (
            rule.startswith(_BYPASS_RULE_PREFIX)
            or rule.startswith(_LEGACY_BYPASS_WILDCARD_RULE_PREFIX)
            or rule in _KNOWN_BYPASS_DOMAIN_RULES
        )
        and rule.endswith(_BYPASS_RULE_SUFFIX)
    )

def _sync_process_bypass_rules(
    data: dict[str, Any],
    desired: list[str],
) -> bool:
    """Ensure the *rules* list starts with exactly the desired bypass entries.

    Managed rules sit at the top of the list so they are evaluated before
    any other rule. Existing managed rules are replaced; non-managed rules
    are left untouched.
    """
    rules = data.get("rules")
    if not isinstance(rules, list):
        if not desired:
            return False
        rules = []
        data["rules"] = rules

    # Strip all existing managed bypass rules from the top.
    old_managed: list[str] = []
    while rules and _is_managed_bypass_rule(rules[0]):
        old_managed.append(rules.pop(0))

    desired_domains = _expand_process_bypass_domain_suffixes(desired)
    new_managed = [
        f"{_BYPASS_RULE_PREFIX}{name}{_BYPASS_RULE_SUFFIX}"
        for name in desired
    ] + [
        f"{_DOMAIN_BYPASS_RULE_PREFIX}{domain}{_BYPASS_RULE_SUFFIX}"
        for domain in desired_domains
    ]

    if new_managed == old_managed:
        # Put them back — nothing to change.
        for i, rule in enumerate(old_managed):
            rules.insert(i, rule)
        return False

    # Insert new managed rules at the top.
    for i, rule in enumerate(new_managed):
        rules.insert(i, rule)
    return True


def _expand_process_bypass_names(raw: str | list[str]) -> list[str]:
    if isinstance(raw, str):
        requested = [
            name.strip()
            for name in raw.split(",")
            if name.strip()
        ]
    else:
        requested = [
            str(name).strip()
            for name in raw
            if str(name).strip()
        ]
    if not requested:
        return []

    running = _running_process_names()
    expanded: list[str] = []
    seen: set[str] = set()
    for name in requested:
        for candidate in _matching_process_names(name, running):
            if candidate in seen:
                continue
            seen.add(candidate)
            expanded.append(candidate)
    return expanded


def _expand_process_bypass_domain_suffixes(raw: str | list[str]) -> list[str]:
    names = _expand_process_bypass_names(raw)
    if not names:
        return []

    domains: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = name.strip().casefold()
        for domain in _KNOWN_PROCESS_BYPASS_DOMAIN_SUFFIXES.get(normalized, []):
            if domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)
    return domains


def _running_process_names() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm="],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _matching_process_names(name: str, running: list[str]) -> list[str]:
    normalized = name.strip()
    if not normalized:
        return []

    lowered = normalized.lower()
    matches: list[str] = [normalized]
    for candidate in running:
        candidate_lower = candidate.lower()
        if candidate_lower == lowered:
            if candidate not in matches:
                matches.append(candidate)
            continue
        if candidate_lower.startswith(lowered) and len(candidate_lower) > len(lowered):
            next_char = candidate_lower[len(lowered)]
            if next_char in {"_", "-", ".", " "} and candidate not in matches:
                matches.append(candidate)
    return matches


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
