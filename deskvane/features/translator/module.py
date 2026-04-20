from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import HotkeySpec, SettingsGroupSpec, SettingsSectionSpec, TraySectionContribution
from ...feature_module import FeatureModule
from ...ui.tray_actions import TrayAction, TrayMenuItem, build_translator_status_line


class TranslatorFeatureModule(FeatureModule):
    name = "translator.runtime"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context
        context.tasks.register("translator", context.app.translator.start, context.app.translator.stop)

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def contribute_hotkeys(self) -> tuple[HotkeySpec, ...]:
        return (
            HotkeySpec(
                "translator.toggle_pause",
                "translator",
                "hotkey_toggle_pause",
                "<ctrl>+<alt>+t",
                "暂停/恢复监控快捷键",
                "translator_toggle_pause",
            ),
        )

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="translator",
                label="翻译",
                config_attr="translator",
                summary="监听、请求和弹窗都在这里。",
                order=30,
                groups=(
                    SettingsGroupSpec("监听与展示", "哪些输入会触发翻译，以及如何展示结果。", ("enabled", "selection_enabled", "clipboard_enabled", "popup_enabled", "auto_copy", "hotkey_toggle_pause", "popup_width_px")),
                    SettingsGroupSpec("模型请求", "请求频率、超时和输出长度。", ("ollama_host", "model", "source_language", "target_language", "poll_interval_ms", "debounce_ms", "request_timeout_s", "max_output_tokens", "keep_alive", "disable_thinking")),
                    SettingsGroupSpec("文本范围", "避免过短或过长的输入。", ("min_chars", "max_chars", "prompt_extra")),
                ),
            ),
        )

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return (
            TraySectionContribution(
                section="translator",
                order=10,
                build_entries=lambda state: (
                    TrayMenuItem(build_translator_status_line(state), enabled=False),
                    TrayMenuItem("复制最近译文", TrayAction.TRANSLATOR_COPY_LAST, default=True, enabled=state.translator_enabled and state.last_translation_available),
                    TrayMenuItem("恢复监控" if state.translator_paused else "暂停监控", TrayAction.TRANSLATOR_TOGGLE_PAUSE, enabled=state.translator_enabled),
                ),
            ),
        )
