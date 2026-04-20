from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import HotkeySpec, SettingsGroupSpec, SettingsSectionSpec, TraySectionContribution
from ...feature_module import FeatureModule
from ...ui.tray_actions import TrayAction, TrayMenuItem


class ClipboardHistoryFeatureModule(FeatureModule):
    name = "clipboard_history"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def contribute_hotkeys(self) -> tuple[HotkeySpec, ...]:
        return (
            HotkeySpec(
                "clipboard.history",
                "general",
                "hotkey_clipboard_history",
                "<alt>+v",
                "剪贴板历史快捷键",
                "show_clipboard_history",
                enabled_when=lambda app: bool(getattr(app.config.general, "clipboard_history_enabled", True)),
            ),
        )

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return ()

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return (
            TraySectionContribution(
                section="tools",
                order=20,
                build_entries=lambda state: (
                    TrayMenuItem("剪贴板历史", TrayAction.SHOW_CLIPBOARD_HISTORY, enabled=state.clipboard_history_enabled),
                ),
            ),
        )
