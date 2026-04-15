from __future__ import annotations

import os
import queue
import re
import subprocess
import tkinter as tk
from pathlib import Path

from .log import get_logger

_logger = get_logger("app")

from .config import CONFIG_PATH, AppConfig, _save_config, load_config
from .git_proxy import GitProxyManager
from .hotkeys import HotkeyManager
from .notifier import Notifier
from .screenshot import ScreenshotTool
from .translator.engine import TranslatorEngine
from .tray import TrayController
from .terminal_proxy import TerminalProxyManager
from .clipboard_history import ClipboardHistoryManager
from .subconverter import SubconverterServer
from .subconverter.service import load_subscription_proxies
from .mihomo import MihomoManager

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

    def __init__(self) -> None:
        # Tkinter root (hidden)
        self.root = tk.Tk()
        self._app_icon_image = _apply_tk_icon(self.root)
        self.root.withdraw()

        # Core services
        self.dispatcher = UiDispatcher(self.root)
        self.notifier = Notifier()
        self.config = load_config()

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

        # Hotkeys
        self.hotkeys = HotkeyManager(self)
        self.hotkeys.register(
            self.config.screenshot.hotkey,
            self.do_screenshot,
        )
        self.hotkeys.register(
            self.config.screenshot.hotkey_pin,
            self.do_screenshot_and_pin,
        )
        self.hotkeys.register(
            self.config.screenshot.hotkey_interactive,
            self.do_screenshot_interactive,
        )
        self.hotkeys.register(
            self.config.screenshot.hotkey_pin_clipboard,
            self.do_pin_clipboard,
        )
        
        if getattr(self.config.general, "clipboard_history_enabled", True):
            self.hotkeys.register(
                getattr(self.config.general, "hotkey_clipboard_history", "<alt>+v"),
                self.show_clipboard_history,
            )
            
        self.hotkeys.register(
            getattr(self.config.screenshot, "hotkey_pure_ocr", "<alt>+<f1>"),
            self.do_pure_ocr,
        )
        self.hotkeys.register(
            getattr(self.config.translator, "hotkey_toggle_pause", "<ctrl>+<alt>+t"),
            self.translator_toggle_pause,
        )

        # Tray
        self.tray = TrayController(self)

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def run(self) -> None:
        self.tray.start()
        self.hotkeys.start()
        self.translator.start()
        if self.subconverter_server:
            self.subconverter_server.start()
        if getattr(self.config.mihomo, "autostart", False):
            self.mihomo_manager.start()
            self.tray.refresh()
            self.tray.rebuild_menu()
            self.root.after(1200, self.tray.refresh)
            self.root.after(1200, self.tray.rebuild_menu)

        # Terminal Proxy Integration
        TerminalProxyManager.setup_hooks()
        self.terminal_proxy_status_display = "未知"
        self._refresh_proxy_display()

        # Main TK Loop
        if not self.tray.supports_menu:
            self.notifier.show(
                "托盘菜单受限",
                "当前 pystray 后端不支持完整菜单。建议安装 python3-gi 和 Ayatana AppIndicator。",
            )
        self.root.mainloop()

    def quit(self) -> None:
        if self.subconverter_server:
            self.subconverter_server.stop()
        self.mihomo_manager.stop_all()
        self.translator.stop()
        self.hotkeys.stop()
        self.tray.stop()
        self.root.after(50, self.root.quit)

    def show_subconverter(self) -> None:
        from .subconverter.gui import SubconverterDialog
        self.dispatcher.call_soon(lambda: SubconverterDialog(self))

    def show_help(self) -> None:
        def _open():
            import webbrowser
            from .help_doc import generate_help_html
            try:
                path = generate_help_html(self.config)
                webbrowser.open(path.as_uri())
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
            return TerminalProxyManager.get_status().enabled
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
            TerminalProxyManager.enable(self.config.proxy.address)
            self._refresh_proxy_display()
            if self.config.general.notifications_enabled:
                self.notifier.show("终端代理已注入", "新开此后的终端窗口将默认走代理。并且任何终端均可输入 'proxy' 随时切换！")
        except Exception as exc:
            self.notifier.show("Terminal Proxy 设置失败", str(exc))

    def disable_terminal_proxy(self) -> None:
        try:
            TerminalProxyManager.disable(self.config.proxy.address)
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
            status = TerminalProxyManager.get_status()
            self.terminal_proxy_status_display = "已开启 (新终端有效)" if status.enabled else "未开启"
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
        from .settings_panel import open_settings
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
        if self.mihomo_manager.backend == "core":
            from .mihomo.panel import open_mihomo_panel
            open_mihomo_panel(self)
            return
        self.mihomo_manager.show_window()

    def open_mihomo_controller(self) -> None:
        self.mihomo_manager.open_controller()

    def open_mihomo_core_config(self) -> None:
        status = self.mihomo_manager.get_core_status()
        target = status.config_path if status.config_exists else status.home_dir
        try:
            subprocess.Popen(["xdg-open", target])
        except FileNotFoundError:
            self.notifier.show("无法打开 Mihomo 配置", target)

    def open_mihomo_logs(self) -> None:
        status = self.mihomo_manager.get_core_status()
        target = status.logs_dir if os.path.isdir(status.logs_dir) else status.home_dir
        try:
            subprocess.Popen(["xdg-open", target])
        except FileNotFoundError:
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
            _save_config(self.config)
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
        _save_config(self.config)
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
        _save_config(self.config)
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
        _save_config(self.config)

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
        new_state = not self.config.mihomo.pac_enabled
        self.config.mihomo.pac_enabled = new_state
        _save_config(self.config)

        # Start or stop the PAC server
        self.mihomo_manager.set_pac_enabled(new_state)

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

        self.config.mihomo.pac_remote_url = remote_url.strip()
        self.config.mihomo.pac_proxy_domains = proxy_domains.strip()
        self.config.mihomo.pac_direct_domains = direct_domains.strip()
        normalized_action = default_action.strip().upper()
        if normalized_action not in {"PROXY", "DIRECT"}:
            normalized_action = "PROXY"
        self.config.mihomo.pac_default_action = normalized_action
        if pac_port is not None:
            self.config.mihomo.pac_port = max(1024, min(65535, pac_port))
        _save_config(self.config)

        # Clear remote PAC cache so next request fetches fresh content
        if remote_url.strip():
            invalidate_remote_pac_cache(remote_url.strip())

        # Restart PAC server if running
        if self.config.mihomo.pac_enabled:
            self.mihomo_manager.restart_pac()

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
            self.config = load_config()
        except Exception as exc:
            self.notifier.show("配置加载失败", str(exc))
            return
        self.mihomo_manager.reload_config()
        self.translator.reload()
        self._refresh_proxy_display()

        # Re-register hotkeys with potentially new bindings
        self.hotkeys.clear()
        self.hotkeys.register(self.config.screenshot.hotkey, self.do_screenshot)
        self.hotkeys.register(self.config.screenshot.hotkey_pin, self.do_screenshot_and_pin)
        self.hotkeys.register(self.config.screenshot.hotkey_interactive, self.do_screenshot_interactive)
        self.hotkeys.register(self.config.screenshot.hotkey_pin_clipboard, self.do_pin_clipboard)
        self.hotkeys.register(
            getattr(self.config.screenshot, "hotkey_pure_ocr", "<alt>+<f1>"),
            self.do_pure_ocr,
        )
        self.hotkeys.register(
            getattr(self.config.translator, "hotkey_toggle_pause", "<ctrl>+<alt>+t"),
            self.translator_toggle_pause,
        )
        if getattr(self.config.general, "clipboard_history_enabled", True):
            self.hotkeys.register(
                getattr(self.config.general, "hotkey_clipboard_history", "<alt>+v"),
                self.show_clipboard_history,
            )
        self.hotkeys.restart()
        self.tray.rebuild_menu()

        if self.config.general.notifications_enabled:
            self.notifier.show("配置已重载", "")

    def open_config(self) -> None:
        try:
            subprocess.Popen(["xdg-open", str(CONFIG_PATH)])
        except FileNotFoundError:
            self.notifier.show("无法打开配置", str(CONFIG_PATH))
