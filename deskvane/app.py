from __future__ import annotations

import queue
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
from .features.proxy.git_proxy import GitProxyManager
from .features.proxy.state import ProxyState
from .features.shell.hotkeys import HotkeyManager
from .features.shell.notifications import Notifier
from .features.shell.state import ShellState
from .features.subconverter.state import SubconverterState
from .platform.base import PlatformServices
from .platform.factory import get_platform_services
from .features.capture.tool import ScreenshotTool
from .translator.engine import TranslatorEngine
from .ui import TrayController
from .features.clipboard_history.manager import ClipboardHistoryManager
from .subconverter import SubconverterServer

if TYPE_CHECKING:
    from .app_context import ModuleContext

_APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "deskvane-icon.png"


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
        self.notifier = Notifier(self.platform_services.notification)

        # Modules
        self.screenshot_tool = ScreenshotTool(self)
        self.translator = TranslatorEngine(self)
        self.clipboard_history = ClipboardHistoryManager(self)

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
            autostart_enabled=bool(getattr(self.config.general, "autostart_enabled", False)),
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
    # Config
    # ---------------------------------------------------------------

    def reload_config(self) -> None:
        try:
            self.config = self.config_manager.load()
        except Exception as exc:
            self.notifier.show("配置加载失败", str(exc))
            return
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
