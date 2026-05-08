from __future__ import annotations

from dataclasses import dataclass

from .tray_model import TrayMenuItem, TrayMenuModel, TrayMenuSeparator


class TrayAction:
    DO_SCREENSHOT_AND_PIN = "do_screenshot_and_pin"
    DO_PURE_OCR = "do_pure_ocr"
    SHOW_CLIPBOARD_HISTORY = "show_clipboard_history"
    SHOW_SUBCONVERTER = "show_subconverter"
    TOGGLE_TERMINAL_PROXY = "toggle_terminal_proxy"
    TOGGLE_GIT_PROXY = "toggle_git_proxy"
    TRANSLATOR_COPY_LAST = "translator_copy_last"
    TRANSLATOR_TOGGLE_PAUSE = "translator_toggle_pause"
    SHOW_SETTINGS = "show_settings"
    SHOW_HELP = "show_help"
    QUIT = "quit"


@dataclass(frozen=True, slots=True)
class TrayMenuState:
    translator_enabled: bool
    translator_paused: bool
    last_translation_available: bool
    clipboard_history_enabled: bool
    is_git_proxy_enabled: bool
    is_terminal_proxy_enabled: bool
    terminal_proxy_supported: bool


def build_translator_status_line(state: TrayMenuState) -> str:
    if not state.translator_enabled:
        return "状态: 未启用"
    return f"状态: {'已暂停' if state.translator_paused else '运行中'}"


def build_tray_menu_model(state: TrayMenuState, registry) -> TrayMenuModel:
    if registry is None:
        raise RuntimeError("DeskVane tray menu requires tray registry context")

    tools_sub = registry.build_entries("tools", state)
    proxy_sub = registry.build_entries("proxy", state)
    translator_sub = registry.build_entries("translator", state)

    return TrayMenuModel(
        items=(
            TrayMenuItem("工具", submenu=tools_sub),
            TrayMenuItem("代理", submenu=proxy_sub),
            TrayMenuItem("翻译", submenu=translator_sub),
            TrayMenuSeparator(),
            TrayMenuItem("设置…", TrayAction.SHOW_SETTINGS),
            TrayMenuItem("帮助", TrayAction.SHOW_HELP),
            TrayMenuSeparator(),
            TrayMenuItem("退出", TrayAction.QUIT),
        )
    )
