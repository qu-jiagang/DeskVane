from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import HotkeySpec, SettingsGroupSpec, SettingsSectionSpec, TraySectionContribution
from ...feature_module import FeatureModule
from ...ui.tray_actions import TrayAction, TrayMenuItem


class CaptureFeatureModule(FeatureModule):
    name = "capture"

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
            HotkeySpec("screenshot.capture", "screenshot", "hotkey", "<ctrl>+<shift>+a", "截图快捷键", "do_screenshot"),
            HotkeySpec("screenshot.pin", "screenshot", "hotkey_pin", "<f1>", "截图钉图快捷键", "do_screenshot_and_pin"),
            HotkeySpec("screenshot.interactive", "screenshot", "hotkey_interactive", "<ctrl>+<f1>", "交互式截图快捷键", "do_screenshot_interactive"),
            HotkeySpec("screenshot.pin_clipboard", "screenshot", "hotkey_pin_clipboard", "<f3>", "钉贴剪贴板快捷键", "do_pin_clipboard"),
            HotkeySpec("screenshot.pure_ocr", "screenshot", "hotkey_pure_ocr", "<alt>+<f1>", "纯 OCR 快捷键", "do_pure_ocr"),
        )

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="capture",
                label="截图",
                config_attr="screenshot",
                summary="先设置保存策略，再调整快捷键。",
                order=20,
                groups=(
                    SettingsGroupSpec("截图行为", "保存和复制的默认方式。", ("save_dir", "copy_to_clipboard", "save_to_disk", "notifications_enabled")),
                    SettingsGroupSpec("快捷键", "保存后会立即重绑。", ("hotkey", "hotkey_pin", "hotkey_pure_ocr", "hotkey_interactive", "hotkey_pin_clipboard")),
                ),
            ),
        )

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return (
            TraySectionContribution(
                section="tools",
                order=10,
                build_entries=lambda _state: (
                    TrayMenuItem("截图并钉住", TrayAction.DO_SCREENSHOT_AND_PIN, default=True),
                    TrayMenuItem("纯 OCR", TrayAction.DO_PURE_OCR),
                ),
            ),
        )
