from __future__ import annotations

import os

from ...app_context import ModuleContext
from ...core.contributions import SettingsGroupSpec, SettingsSectionSpec
from ...feature_module import FeatureModule


class TrayFeatureModule(FeatureModule):
    name = "shell.tray"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context
        if os.environ.get("DESKVANE_DISABLE_TRAY") != "1":
            context.tasks.register("tray", context.app.tray.start, context.app.tray.stop)

    def start(self) -> None:
        if self._context is None:
            raise RuntimeError("tray module has not been registered")
        app = self._context.app
        if hasattr(app, "get_shell_state"):
            shell_state = app.get_shell_state()
        else:
            shell_state = type("_ShellState", (), {"tray_supports_menu": bool(getattr(app.tray, "supports_menu", True))})()
        if not shell_state.tray_supports_menu:
            app.notifier.show(
                "托盘菜单受限",
                "当前 pystray 后端不支持完整菜单。建议安装 python3-gi 和 Ayatana AppIndicator。",
            )

    def stop(self) -> None:
        return


class HotkeyFeatureModule(FeatureModule):
    name = "shell.hotkeys"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context
        if os.environ.get("DESKVANE_DISABLE_HOTKEYS") != "1":
            context.tasks.register("hotkeys", context.app.hotkeys.start, context.app.hotkeys.stop)

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="general",
                label="通用",
                config_attr="general",
                summary="日常行为、通知和剪贴板历史。",
                order=10,
                groups=(SettingsGroupSpec("日常体验", "通知、快捷入口和托盘展示。", ("notifications_enabled", "clipboard_history_enabled", "hotkey_clipboard_history", "tray_display")),),
            ),
        )
