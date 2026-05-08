from __future__ import annotations

from types import SimpleNamespace

from deskvane.config import AppConfig
from deskvane.core.runtime_api import RuntimeApi
from deskvane.core.runtime_events import RuntimeEventStore
from deskvane.runtime_sidecar import HeadlessRuntimeApp, _TranslationPopupBridge
import pytest


class _ConfigManager:
    def __init__(self) -> None:
        self.config = AppConfig()
        self.saved = 0
        self.loaded = 0

    def load(self) -> AppConfig:
        self.loaded += 1
        return self.config

    def save(self, config: AppConfig) -> None:
        self.saved += 1
        self.config = config


def test_headless_runtime_exposes_state_without_tk() -> None:
    app = HeadlessRuntimeApp(config_manager=_ConfigManager())
    api = RuntimeApi(app, events=app.events)

    state = api.get_state()

    assert state["capture"]["copy_to_clipboard"] is True
    assert state["clipboard_history"]["overlay_visible"] is False
    assert state["translator"]["backend_label"] == "python-sidecar"
    assert state["shell"]["tray_supports_menu"] is True
    assert "system" in state
    assert api.action_names() == (
        "app.quit",
        "capture.interactive_screenshot",
        "capture.pin_clipboard",
        "capture.pure_ocr",
        "capture.screenshot",
        "capture.screenshot_and_pin",
        "clipboard.show_history",
        "help.show",
        "proxy.toggle_git",
        "proxy.toggle_terminal",
        "settings.show",
        "subconverter.show",
        "translator.copy_last",
        "translator.retry_last",
        "translator.toggle_pause",
    )
    app.quit()


def test_translation_popup_formats_long_single_line_for_reading() -> None:
    text = (
        "我们首先介绍我们的第一代理模型：DeepSeek-R1-Zero 和 DeepSeek-R1。 "
        "DeepSeek-R1-Zero 通过大规模强化学习训练。 "
        "然而，它面临可读性差、语言混合等挑战。 "
        "为了改善这些问题，我们引入了 DeepSeek-R1。 "
        "DeepSeek-R1 在推理任务上的表现与 OpenAI-o1-1217 相当。 "
        "我们开源了 DeepSeek-R1-Zero、DeepSeek-R1 以及基于 DeepSeek-R1 蒸馏出的模型。"
    )

    formatted = _TranslationPopupBridge._format_display_text(text)

    assert "\n\n" in formatted
    assert "然而" in formatted
    assert formatted.startswith("我们首先介绍")


def test_headless_runtime_updates_config() -> None:
    manager = _ConfigManager()
    app = HeadlessRuntimeApp(config_manager=manager)
    api = RuntimeApi(app, events=app.events)

    updated = api.update_config({"general": {"tray_display": "gpu_mem"}, "subconverter": {"port": "8888"}})

    assert updated["general"]["tray_display"] == "gpu_mem"
    assert app.config.subconverter.port == 8888
    assert manager.saved == 1
    assert manager.loaded == 2
    app.quit()


def test_headless_runtime_records_unsupported_ui_actions() -> None:
    events = RuntimeEventStore()
    app = HeadlessRuntimeApp(config_manager=_ConfigManager(), events=events)

    try:
        app._unsupported("missing.action")
    except RuntimeError as exc:
        assert "legacy Tk runtime" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert events.list(limit=1)[0].topic == "action.unsupported"
    app.quit()


def test_headless_runtime_forwards_legacy_actions(monkeypatch) -> None:
    app = HeadlessRuntimeApp(config_manager=_ConfigManager())
    calls: list[str] = []

    monkeypatch.setattr(app, "_ensure_legacy_runtime", lambda: calls.append("ensure"))
    monkeypatch.setattr(app, "_post_legacy_action", lambda action: calls.append(action))

    app.do_screenshot_and_pin()

    assert calls == ["ensure", "capture.screenshot_and_pin"]
    assert app.events.list(limit=1)[0].topic == "legacy.action"
    app.quit()


def test_headless_runtime_selects_clipboard_history(monkeypatch) -> None:
    app = HeadlessRuntimeApp(config_manager=_ConfigManager())
    app.clipboard_history = ["alpha", "beta"]
    written: list[str] = []

    monkeypatch.setattr(app.platform_services.clipboard, "write_text", lambda text: written.append(text) or True)

    selected = app.select_clipboard_history_item(1)

    assert selected["text"] == "beta"
    assert written == ["beta"]
    assert app.clipboard_history[:2] == ["beta", "alpha"]
    app.quit()


def test_headless_runtime_toggles_translator_pause() -> None:
    manager = _ConfigManager()
    manager.config.translator.enabled = True
    app = HeadlessRuntimeApp(config_manager=manager)

    assert app.get_translator_state().paused is True

    app.translator_toggle_pause()

    state = app.get_translator_state()
    assert state.paused is False
    assert state.running is True
    assert state.status_key == "ready"
    app.quit()


def test_headless_runtime_translates_text(monkeypatch) -> None:
    manager = _ConfigManager()
    manager.config.translator.enabled = True
    app = HeadlessRuntimeApp(config_manager=manager)
    app.translator_toggle_pause()

    class _Client:
        def translate(self, **kwargs):
            assert kwargs["text"] == "hello"
            return SimpleNamespace(text="你好", model="fake-model", elapsed_ms=7)

    monkeypatch.setattr(app, "_build_translator_client", lambda: _Client())

    result = app.translate_text("hello")

    assert result == {"text": "你好", "model": "fake-model", "elapsed_ms": 7}
    assert app.get_translator_state().last_translation_available is True
    assert app.get_translator_state().last_translation_preview == "你好"
    app.quit()


def test_headless_runtime_auto_translates_clipboard_text(monkeypatch) -> None:
    manager = _ConfigManager()
    manager.config.translator.enabled = True
    manager.config.translator.debounce_ms = 0
    manager.config.translator.popup_enabled = True
    app = HeadlessRuntimeApp(config_manager=manager)
    app.translator_toggle_pause()
    shown = []
    loading = []

    class _Client:
        def translate(self, **kwargs):
            assert kwargs["text"] == "hello"
            return SimpleNamespace(text="你好", model="fake-model", elapsed_ms=7)

    monkeypatch.setattr(app, "_build_translator_client", lambda: _Client())
    monkeypatch.setattr(app._translation_popup, "show_loading", lambda text, width: loading.append((text, width)))
    monkeypatch.setattr(app._translation_popup, "show", lambda text, width: shown.append((text, width)))

    app._auto_translate_text("hello")

    assert app.last_translation == "你好"
    assert loading == [("hello", manager.config.translator.popup_width_px)]
    assert shown == [("你好", manager.config.translator.popup_width_px)]
    assert app.events.list(limit=1)[0].topic == "translator.auto_translated"
    app.quit()


def test_headless_runtime_starts_and_stops_subconverter_server() -> None:
    manager = _ConfigManager()
    manager.config.subconverter.port = 0

    app = HeadlessRuntimeApp(config_manager=manager)

    if not app.get_subconverter_state().running:
        pytest.skip("local socket binding is unavailable in this environment")

    app.config.subconverter.enable_server = False
    app.config_manager.save(app.config)
    app.reload_config()

    assert app.get_subconverter_state().running is False
