from __future__ import annotations

import os
import queue
import re
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from .log import get_logger

_logger = get_logger("app")

from .config import CONFIG_PATH, AppConfig, _save_config, load_config
from .core import ConfigManager
from .features.capture.state import CaptureState
from .features.clipboard_history.state import ClipboardHistoryState
from .features.mihomo.state import MihomoFeatureState
from .features.proxy.git_proxy import GitProxyManager
from .features.proxy.state import ProxyState
from .features.shell.hotkeys import HotkeyManager
from .features.shell.notifications import Notifier
from .features.shell.state import ShellState
from .features.subconverter.state import SubconverterState
from .mihomo.api import MihomoRuntimeState
from .mihomo.core_manager import MihomoCoreStatus
from .platform.base import PlatformServices
from .platform.factory import get_platform_services
from .features.capture.tool import ScreenshotTool
from .translator.engine import TranslatorEngine
from .ui import TrayController
from .features.clipboard_history.manager import ClipboardHistoryManager
from .subconverter import SubconverterServer
from .subconverter.service import load_subscription_proxies
from .mihomo import MihomoManager

if TYPE_CHECKING:
    from .app_context import ModuleContext

_APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "deskvane-icon.png"


def _normalize_process_list(raw: str) -> str:
    tokens = [
        token.strip()
        for token in re.split(r"[\s,，;；\n\r\t]+", raw)
        if token.strip()
    ]
    normalized: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(token)
    return ", ".join(normalized)


def _merge_saved_subscription_urls(current: str, saved: list[str] | None, limit: int = 8) -> list[str]:
    ordered = [current, *(saved or [])]
    merged: list[str] = []
    seen: set[str] = set()
    for raw in ordered:
        normalized = str(raw).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged[:limit]


def _apply_tk_icon(window: tk.Misc) -> tk.PhotoImage | None:
    if not _APP_ICON_PATH.exists():
        return None
    try:
        image = tk.PhotoImage(file=str(_APP_ICON_PATH))
        window.iconphoto(True, image)
        return image
    except Exception:
        return None


def _normalize_platform_specific_config(config: AppConfig, platform_services: PlatformServices) -> bool:
    changed = False
    if not platform_services.info.supports_mihomo_party and config.mihomo.backend == "party":
        config.mihomo.backend = "core"
        changed = True
    return changed


class UiDispatcher:
    """Thread-safe dispatcher that funnels callbacks into the tkinter main loop."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._queue: queue.Queue[tuple] = queue.Queue()
        self.root.after(40, self._drain)

    def call_soon(self, fn, *args, **kwargs) -> None:
        self._queue.put((fn, args, kwargs))

    def _drain(self) -> None:
        while True:
            try:
                fn, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                import traceback
                _logger.error("dispatch error: %s\n%s", exc, traceback.format_exc())
        self.root.after(40, self._drain)


class DeskVaneApp:
    """Main application coordinating all tools."""

    def __init__(
        self,
        platform_services: PlatformServices | None = None,
        config_manager: ConfigManager | None = None,
        context: ModuleContext | SimpleNamespace | None = None,
    ) -> None:
        # Tkinter root (hidden)
        self.root = tk.Tk()
        self._app_icon_image = _apply_tk_icon(self.root)
        self.root.withdraw()

        # Core services
        self.dispatcher = UiDispatcher(self.root)
        self.platform_services = platform_services or get_platform_services()
        self.config_manager = config_manager or ConfigManager()
        self.context: ModuleContext | SimpleNamespace | None = context
        self._runtime_started = False
        self.config = self.config_manager.load()
        if _normalize_platform_specific_config(self.config, self.platform_services):
            self._save_current_config()
        self.notifier = Notifier(self.platform_services.notification)

        # Modules
        self.screenshot_tool = ScreenshotTool(self)
        self.translator = TranslatorEngine(self)
        self.clipboard_history = ClipboardHistoryManager(self)
        
        self.mihomo_manager = MihomoManager(self.notifier, lambda: self.config.mihomo)
        
        self.subconverter_server = None
        if getattr(self.config, "subconverter", None) and getattr(self.config.subconverter, "enable_server", True):
            self.subconverter_server = SubconverterServer(self.config.subconverter.port)
            
        try:
            self.git_proxy_status_display = GitProxyManager.get_status().display
        except Exception:
            self.git_proxy_status_display = "未知"
        self.terminal_proxy_status_display = "未知"

        self.hotkeys = HotkeyManager(self)

        # Tray
        self.tray = TrayController(self)

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def _save_current_config(self) -> None:
        config_manager = getattr(self, "config_manager", None)
        if config_manager is None:
            _save_config(self.config)
            return
        config_manager.save(self.config)

    def start_runtime(self) -> None:
        if self._runtime_started:
            return
        if self.context is None:
            raise RuntimeError("DeskVaneApp requires ModuleContext before starting runtime")
        self._runtime_started = True

    def stop_runtime(self) -> None:
        if not self._runtime_started:
            return
        self._runtime_started = False

    def enter_mainloop(self) -> None:
        self.root.mainloop()

    def run(self) -> None:
        self.start_runtime()
        self.enter_mainloop()

    def quit(self) -> None:
        self.stop_runtime()
        self.root.after(50, self.root.quit)

    def show_subconverter(self) -> None:
        from .subconverter.gui import SubconverterDialog
        self.dispatcher.call_soon(lambda: SubconverterDialog(self))

    def show_help(self) -> None:
        def _open():
            from .ui.help_doc import generate_help_html
            try:
                path = generate_help_html(self.config)
                if not self.platform_services.opener.open_path(path):
                    self.notifier.show("打开帮助失败", str(path))
            except Exception as e:
                self.notifier.show("打开帮助失败", str(e))
        self.dispatcher.call_soon(_open)

    # ---------------------------------------------------------------
    # Screenshot
    # ---------------------------------------------------------------

    def do_screenshot(self) -> None:
        self.dispatcher.call_soon(self.screenshot_tool.take_screenshot)

    def do_screenshot_and_pin(self) -> None:
        self.dispatcher.call_soon(self.screenshot_tool.take_screenshot_and_pin)

    def do_screenshot_interactive(self) -> None:
        self.dispatcher.call_soon(self.screenshot_tool.take_screenshot_interactive)
        
    def do_pure_ocr(self) -> None:
        self.dispatcher.call_soon(self.screenshot_tool.take_pure_ocr)

    def do_pin_clipboard(self) -> None:
        self.dispatcher.call_soon(self.screenshot_tool.pin_clipboard)

    def submit_ocr(self, b64_payload: str) -> None:
        """Accept an OCR request from the screenshot tool (decoupled)."""
        self.translator.submit_pure_ocr(b64_payload)

    def show_clipboard_history(self) -> None:
        self.dispatcher.call_soon(self.clipboard_history.show_overlay)

    def get_capture_state(self) -> CaptureState:
        cfg = self.config.screenshot
        return CaptureState(
            save_dir=str(cfg.save_dir),
            copy_to_clipboard=bool(cfg.copy_to_clipboard),
            save_to_disk=bool(cfg.save_to_disk),
            notifications_enabled=bool(cfg.notifications_enabled),
        )

    def get_clipboard_history_state(self) -> ClipboardHistoryState:
        overlay = getattr(self.clipboard_history, "_overlay", None)
        overlay_visible = bool(overlay and getattr(overlay, "top", None) and overlay.top.winfo_exists())
        return ClipboardHistoryState(
            enabled=bool(getattr(self.config.general, "clipboard_history_enabled", True)),
            item_count=len(getattr(self.clipboard_history, "history", [])),
            overlay_visible=overlay_visible,
        )

    def get_translator_state(self):
        return self.translator.snapshot_state()

    def get_shell_state(self) -> ShellState:
        tray = getattr(self, "tray", None)
        return ShellState(
            tray_supports_menu=bool(getattr(tray, "supports_menu", True)),
            notifications_enabled=bool(getattr(self.config.general, "notifications_enabled", True)),
            clipboard_history_enabled=bool(getattr(self.config.general, "clipboard_history_enabled", True)),
            git_proxy_enabled=self.is_git_proxy_enabled,
            terminal_proxy_enabled=self.is_terminal_proxy_enabled,
            terminal_proxy_supported=bool(self.platform_services.info.supports_terminal_proxy),
        )

    def get_proxy_state(self) -> ProxyState:
        return ProxyState(
            address=str(self.config.proxy.address),
            git_proxy_enabled=self.is_git_proxy_enabled,
            terminal_proxy_enabled=self.is_terminal_proxy_enabled,
            terminal_proxy_supported=bool(self.platform_services.info.supports_terminal_proxy),
            git_proxy_status_display=str(getattr(self, "git_proxy_status_display", "未知")),
            terminal_proxy_status_display=str(getattr(self, "terminal_proxy_status_display", "未知")),
        )

    @staticmethod
    def _empty_mihomo_runtime(controller: str) -> MihomoRuntimeState:
        return MihomoRuntimeState(
            api_ready=False,
            controller=controller,
            mode="",
            mixed_port=None,
            port=None,
            socks_port=None,
            tun_enabled=False,
            groups=[],
        )

    def get_mihomo_state(self) -> MihomoFeatureState:
        mihomo = self.mihomo_manager
        core_status = mihomo.get_core_status()
        runtime = self._empty_mihomo_runtime(core_status.controller)
        if mihomo.backend == "core" and core_status.api_ready:
            try:
                runtime = mihomo.get_runtime_state()
            except Exception:
                runtime = self._empty_mihomo_runtime(core_status.controller)
        running = core_status.running if mihomo.backend == "core" else mihomo.is_running()
        return MihomoFeatureState(
            installed=bool(mihomo.is_installed()),
            running=bool(running),
            backend=str(mihomo.backend),
            title=str(mihomo.display_name),
            party_supported=bool(self.platform_services.info.supports_mihomo_party),
            has_external_ui=bool(
                self.config.mihomo.external_ui.strip()
                or self.config.mihomo.external_ui_name.strip()
                or self.config.mihomo.external_ui_url.strip()
            ),
            pac_enabled=bool(getattr(self.config.mihomo, "pac_enabled", False)),
            subscription_url=str(getattr(self.config.mihomo, "subscription_url", "")).strip(),
            saved_subscriptions=tuple(
                str(item).strip()
                for item in getattr(self.config.mihomo, "saved_subscriptions", [])
                if str(item).strip()
            ),
            runtime=runtime,
            core_status=core_status,
        )

    def get_subconverter_state(self) -> SubconverterState:
        server = getattr(self, "subconverter_server", None)
        return SubconverterState(
            enabled=bool(getattr(self.config.subconverter, "enable_server", True)),
            port=int(getattr(self.config.subconverter, "port", 7777)),
            running=bool(server and getattr(server, "server", None)),
        )

    # ---------------------------------------------------------------
    # Git Proxy
    # ---------------------------------------------------------------

    @property
    def is_git_proxy_enabled(self) -> bool:
        try:
            return GitProxyManager.get_status().enabled
        except Exception:
            return False

    @property
    def is_terminal_proxy_enabled(self) -> bool:
        try:
            return self.platform_services.proxy_session.is_enabled()
        except Exception:
            return False

    def toggle_git_proxy(self) -> None:
        if self.is_git_proxy_enabled:
            self.disable_git_proxy()
        else:
            self.enable_git_proxy()

    def toggle_terminal_proxy(self) -> None:
        if self.is_terminal_proxy_enabled:
            self.disable_terminal_proxy()
        else:
            self.enable_terminal_proxy()

    def enable_git_proxy(self) -> None:
        try:
            GitProxyManager.enable(self.config.proxy.address)
            self._refresh_proxy_display()
            if self.config.general.notifications_enabled:
                self.notifier.show(
                    "Git Proxy 已开启",
                    self.config.proxy.address,
                )
        except Exception as exc:
            self.notifier.show("Git Proxy 设置失败", str(exc))

    def disable_git_proxy(self) -> None:
        try:
            GitProxyManager.disable()
            self._refresh_proxy_display()
            if self.config.general.notifications_enabled:
                self.notifier.show("Git Proxy 已关闭", "")
        except Exception as exc:
            self.notifier.show("Git Proxy 设置失败", str(exc))

    def enable_terminal_proxy(self) -> None:
        try:
            self.platform_services.proxy_session.enable(self.config.proxy.address)
            self._refresh_proxy_display()
            if self.config.general.notifications_enabled:
                self.notifier.show("终端代理已注入", "新开此后的终端窗口将默认走代理。并且任何终端均可输入 'proxy' 随时切换！")
        except Exception as exc:
            self.notifier.show("Terminal Proxy 设置失败", str(exc))

    def disable_terminal_proxy(self) -> None:
        try:
            self.platform_services.proxy_session.disable(self.config.proxy.address)
            self._refresh_proxy_display()
            if self.config.general.notifications_enabled:
                self.notifier.show("终端代理默认注入已关", "新终端不再默认代理。但依然随时可用 'proxy' 命令！")
        except Exception as exc:
            self.notifier.show("Terminal Proxy 设置失败", str(exc))

    def _refresh_proxy_display(self) -> None:
        try:
            self.git_proxy_status_display = GitProxyManager.get_status().display
        except Exception:
            self.git_proxy_status_display = "未知"
            
        try:
            enabled = self.platform_services.proxy_session.is_enabled()
            self.terminal_proxy_status_display = "已开启 (新终端有效)" if enabled else "未开启"
        except Exception:
            self.terminal_proxy_status_display = "未知"
            
        self.tray.refresh()

    # ---------------------------------------------------------------
    # Translator actions (delegate to engine)
    # ---------------------------------------------------------------

    def translator_copy_last(self) -> None:
        self.translator.copy_last_translation()

    def translator_retry_last(self) -> None:
        self.translator.retry_last_input()

    def translator_toggle_pause(self) -> None:
        self.translator.toggle_pause()
        self.tray.refresh()

    def show_settings(self) -> None:
        from .ui.settings_panel import open_settings
        self.dispatcher.call_soon(lambda: open_settings(self))

    # ---------------------------------------------------------------
    # Mihomo (routed through dispatcher for thread safety)
    # ---------------------------------------------------------------

    def toggle_mihomo(self) -> bool:
        if self.mihomo_manager.is_running():
            self.mihomo_manager.stop()
            ok = True
        else:
            ok = self.mihomo_manager.start()
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def show_mihomo_window(self) -> None:
        if self.mihomo_manager.backend == "core" or not self.platform_services.info.supports_mihomo_party:
            from .mihomo.panel import open_mihomo_panel
            open_mihomo_panel(self)
            return
        self.mihomo_manager.show_window()

    def open_mihomo_controller(self) -> None:
        self.mihomo_manager.open_controller()

    def open_mihomo_core_config(self) -> None:
        status = self.mihomo_manager.get_core_status()
        target = status.config_path if status.config_exists else status.home_dir
        if not self.platform_services.opener.open_path(target):
            self.notifier.show("无法打开 Mihomo 配置", target)

    def open_mihomo_logs(self) -> None:
        status = self.mihomo_manager.get_core_status()
        target = status.logs_dir if os.path.isdir(status.logs_dir) else status.home_dir
        if not self.platform_services.opener.open_path(target):
            self.notifier.show("无法打开 Mihomo 日志目录", target)

    def mihomo_reload_core_config(self) -> bool:
        if self.mihomo_manager.is_running():
            ok = self.mihomo_manager.reload_core_config()
            if ok:
                if self.config.general.notifications_enabled:
                    self.notifier.show("Mihomo 配置已重载", "")
            else:
                detail = self.mihomo_manager.get_core_status().last_error or "请确认 Core 控制 API 已就绪。"
                self.notifier.show("Mihomo 配置重载失败", detail)
        else:
            self.mihomo_manager.reload_config()
            ok = True
            if self.config.general.notifications_enabled:
                self.notifier.show("Mihomo 配置已同步", "Core 当前未运行，下次启动时会自动生效。")
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def mihomo_set_mode(self, mode: str) -> bool:
        ok = self.mihomo_manager.switch_mode(mode)
        if ok:
            if self.config.general.notifications_enabled:
                self.notifier.show("Mihomo 模式已切换", mode)
        else:
            detail = self.mihomo_manager.get_core_status().last_error or mode
            self.notifier.show("Mihomo 模式切换失败", detail)
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def mihomo_toggle_tun(self) -> bool:
        """Toggle TUN mode on the running mihomo core and persist the choice."""
        runtime = self.mihomo_manager.get_runtime_state()
        new_state = not runtime.tun_enabled
        ok = self.mihomo_manager.switch_tun(new_state)
        if ok:
            self.config.mihomo.tun_enabled = new_state
            self._save_current_config()
            reloaded = self.mihomo_manager.reload_core_config()
            if not reloaded:
                detail = self.mihomo_manager.get_core_status().last_error or "TUN 主开关已切换，但运行态配置重载失败。"
                self.notifier.show("Mihomo TUN 切换未完全生效", detail)
                ok = False
            elif self.config.general.notifications_enabled:
                label = "已开启" if new_state else "已关闭"
                self.notifier.show("Mihomo TUN 模式", label)
        else:
            detail = self.mihomo_manager.get_core_status().last_error or "请确认 Core API 已就绪。"
            self.notifier.show("Mihomo TUN 切换失败", detail)
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def mihomo_set_tun_bypass(self, processes: str) -> bool:
        """Save the TUN bypass process list and reload config."""
        normalized = _normalize_process_list(processes)
        self.config.mihomo.tun_direct_processes = normalized
        self._save_current_config()
        running = self.mihomo_manager.is_running()
        closed_connections = 0
        if running:
            ok = self.mihomo_manager.reload_core_config()
            if ok and normalized:
                closed_connections = self.mihomo_manager.refresh_tun_bypass_connections(normalized)
        else:
            self.mihomo_manager.reload_config()
            ok = True
        if self.config.general.notifications_enabled:
            if not ok:
                detail = self.mihomo_manager.get_core_status().last_error or "运行态重载失败。"
                self.notifier.show("TUN 直连程序更新失败", detail)
            elif normalized:
                names = normalized
                if running and closed_connections > 0:
                    detail = f"{names}。已断开 {closed_connections} 条现有连接，等待应用重连。"
                else:
                    detail = names if running else f"{names}。Core 未运行，下次启动自动生效。"
                self.notifier.show("TUN 直连程序已更新", detail)
            else:
                detail = "" if running else "Core 未运行，下次启动自动生效。"
                self.notifier.show("TUN 直连程序已清空", detail)
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def mihomo_switch_proxy(self, group_name: str, proxy_name: str) -> bool:
        ok = self.mihomo_manager.switch_proxy(group_name, proxy_name)
        if ok:
            if self.config.general.notifications_enabled:
                self.notifier.show("Mihomo 代理组已切换", f"{group_name} -> {proxy_name}")
        else:
            self.notifier.show("Mihomo 代理组切换失败", f"{group_name} -> {proxy_name}")
        self.tray.refresh()
        self.tray.rebuild_menu()
        return ok

    def mihomo_test_proxy_delay(
        self,
        proxy_name: str,
        test_url: str,
        timeout_ms: int = 5000,
    ) -> int | None:
        return self.mihomo_manager.test_proxy_delay(
            proxy_name,
            test_url=test_url,
            timeout_ms=timeout_ms,
        )

    def mihomo_save_subscription_url(self, url: str) -> bool:
        normalized = url.strip()
        self.config.mihomo.subscription_url = normalized
        self.config.mihomo.saved_subscriptions = _merge_saved_subscription_urls(
            normalized,
            getattr(self.config.mihomo, "saved_subscriptions", []),
        )
        self._save_current_config()
        if self.config.general.notifications_enabled:
            if normalized:
                self.notifier.show("Mihomo 订阅地址已保存", normalized)
            else:
                self.notifier.show("Mihomo 订阅地址已清空", "")
        return True

    def mihomo_update_subscription(self, source: str | None = None) -> bool:
        subscription_source = (source or self.config.mihomo.subscription_url).strip()
        if not subscription_source:
            self.notifier.show("Mihomo 订阅更新失败", "请先填写订阅地址。")
            return False

        self.config.mihomo.subscription_url = subscription_source
        self.config.mihomo.saved_subscriptions = _merge_saved_subscription_urls(
            subscription_source,
            getattr(self.config.mihomo, "saved_subscriptions", []),
        )
        self._save_current_config()

        try:
            proxies = load_subscription_proxies(subscription_source, timeout_s=10)
            provider_path = self.mihomo_manager.save_subscription_provider(
                proxies,
                subscription_source,
            )
            running = self.mihomo_manager.is_running()
            reloaded = self.mihomo_manager.reload_core_config() if running else False

            if running and not reloaded:
                detail = self.mihomo_manager.get_core_status().last_error or "Core 热重载失败。"
                self.notifier.show(
                    "Mihomo 订阅更新失败",
                    f"Provider 已写入 {provider_path}，但运行态未刷新。{detail}",
                )
                self.tray.refresh()
                self.tray.rebuild_menu()
                return False

            if self.config.general.notifications_enabled:
                if running and reloaded:
                    self.notifier.show(
                        "Mihomo 订阅已更新",
                        f"已写入受管 Provider，并重载到 Core。节点数: {len(proxies)}",
                    )
                else:
                    self.notifier.show(
                        "Mihomo 订阅已保存",
                        f"Provider 已写入 {provider_path}。Core 未运行时会在下次启动后生效。",
                    )
            self.tray.refresh()
            self.tray.rebuild_menu()
            return True
        except Exception as exc:
            self.notifier.show("Mihomo 订阅更新失败", str(exc))
            return False

    def mihomo_switch_subscription(self, source: str) -> bool:
        normalized = source.strip()
        if not normalized:
            self.notifier.show("Mihomo 订阅切换失败", "目标订阅地址为空。")
            return False
        return self.mihomo_update_subscription(normalized)

    # ---------------------------------------------------------------
    # Mihomo PAC
    # ---------------------------------------------------------------

    def mihomo_toggle_pac(self) -> bool:
        """Toggle PAC mode on/off."""
        previous_state = bool(self.config.mihomo.pac_enabled)
        new_state = not self.config.mihomo.pac_enabled
        self.config.mihomo.pac_enabled = new_state
        self._save_current_config()

        # Start or stop the PAC server
        pac_ok = self.mihomo_manager.set_pac_enabled(new_state)
        if not pac_ok:
            self.config.mihomo.pac_enabled = previous_state
            self._save_current_config()
            self.tray.refresh()
            self.tray.rebuild_menu()
            return False

        # Sync PAC rules into Mihomo config for TUN mode
        running = self.mihomo_manager.is_running()
        if running:
            self.mihomo_manager.reload_core_config()

        if self.config.general.notifications_enabled:
            if new_state:
                pac_url = self.mihomo_manager.pac_url
                self.notifier.show("PAC 模式已开启", f"PAC 地址: {pac_url}")
            else:
                self.notifier.show("PAC 模式已关闭", "")
        self.tray.refresh()
        self.tray.rebuild_menu()
        return True

    def mihomo_save_pac_config(
        self,
        proxy_domains: str,
        direct_domains: str,
        default_action: str,
        pac_port: int | None = None,
        remote_url: str = "",
    ) -> bool:
        """Save PAC domain configuration and apply changes."""
        from deskvane.mihomo.pac import invalidate_remote_pac_cache

        previous_remote_url = self.config.mihomo.pac_remote_url
        previous_proxy_domains = self.config.mihomo.pac_proxy_domains
        previous_direct_domains = self.config.mihomo.pac_direct_domains
        previous_default_action = self.config.mihomo.pac_default_action
        previous_pac_port = self.config.mihomo.pac_port
        self.config.mihomo.pac_remote_url = remote_url.strip()
        self.config.mihomo.pac_proxy_domains = proxy_domains.strip()
        self.config.mihomo.pac_direct_domains = direct_domains.strip()
        normalized_action = default_action.strip().upper()
        if normalized_action not in {"PROXY", "DIRECT"}:
            normalized_action = "PROXY"
        self.config.mihomo.pac_default_action = normalized_action
        if pac_port is not None:
            self.config.mihomo.pac_port = max(1024, min(65535, pac_port))
        self._save_current_config()

        # Clear remote PAC cache so next request fetches fresh content
        if remote_url.strip():
            invalidate_remote_pac_cache(remote_url.strip())

        # Restart PAC server if running
        if self.config.mihomo.pac_enabled:
            pac_ok = self.mihomo_manager.restart_pac()
            if not pac_ok:
                self.config.mihomo.pac_remote_url = previous_remote_url
                self.config.mihomo.pac_proxy_domains = previous_proxy_domains
                self.config.mihomo.pac_direct_domains = previous_direct_domains
                self.config.mihomo.pac_default_action = previous_default_action
                self.config.mihomo.pac_port = previous_pac_port
                self._save_current_config()
                if remote_url.strip():
                    invalidate_remote_pac_cache(remote_url.strip())
                if previous_remote_url.strip():
                    invalidate_remote_pac_cache(previous_remote_url.strip())
                self.mihomo_manager.restart_pac()
                self.tray.refresh()
                self.tray.rebuild_menu()
                return False

        # Sync PAC rules into Mihomo config for TUN mode
        running = self.mihomo_manager.is_running()
        if running:
            self.mihomo_manager.reload_core_config()

        if self.config.general.notifications_enabled:
            self.notifier.show("PAC 配置已保存", "规则已更新。")
        self.tray.refresh()
        self.tray.rebuild_menu()
        return True

    def mihomo_copy_pac_url(self) -> None:
        """Copy the PAC URL to clipboard."""
        pac_url = self.mihomo_manager.pac_url
        try:
            if not self.platform_services.clipboard.write_text(pac_url):
                self.root.clipboard_clear()
                self.root.clipboard_append(pac_url)
                self.root.update()
            if self.config.general.notifications_enabled:
                self.notifier.show("PAC 地址已复制", pac_url)
        except Exception as exc:
            self.notifier.show("复制 PAC 地址失败", str(exc))


    # ---------------------------------------------------------------
    # Config
    # ---------------------------------------------------------------

    def reload_config(self) -> None:
        try:
            self.config = self.config_manager.load()
        except Exception as exc:
            self.notifier.show("配置加载失败", str(exc))
            return
        if _normalize_platform_specific_config(self.config, self.platform_services):
            self._save_current_config()
        self.mihomo_manager.reload_config()
        self.translator.reload()
        self._refresh_proxy_display()

        if self.context is None or self.context.hotkey_registry is None:
            raise RuntimeError("DeskVaneApp requires hotkey registry context before reloading config")
        self.context.hotkey_registry.bind(self)
        self.hotkeys.restart()
        self.tray.rebuild_menu()

        if self.config.general.notifications_enabled:
            self.notifier.show("配置已重载", "")

    def open_config(self) -> None:
        if not self.platform_services.opener.open_path(CONFIG_PATH):
            self.notifier.show("无法打开配置", str(CONFIG_PATH))
