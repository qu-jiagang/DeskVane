from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from deskvane.core.runtime_api import RuntimeApi
from deskvane.core.runtime_events import RuntimeEventStore


@dataclass(frozen=True)
class _State:
    enabled: bool
    label: str


class _FakeApp:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reloads = 0
        self.config = SimpleNamespace(
            general=_ConfigSection(notifications_enabled=True, tray_display="default"),
            subconverter=_ConfigSection(port=7777),
        )
        self.config_manager = SimpleNamespace(save=lambda config: self.calls.append("config.save"))

    def get_capture_state(self):
        return _State(True, "capture")

    def get_clipboard_history_state(self):
        return SimpleNamespace(enabled=True, item_count=2)

    def get_translator_state(self):
        return _State(False, "translator")

    def get_shell_state(self):
        return SimpleNamespace(tray_supports_menu=True)

    def get_proxy_state(self):
        return SimpleNamespace(address="http://127.0.0.1:7890")

    def get_subconverter_state(self):
        return SimpleNamespace(enabled=True, running=False)

    def do_screenshot_and_pin(self) -> None:
        self.calls.append("screenshot_and_pin")

    def translate_text(self, text: str):
        self.calls.append(f"translate:{text}")
        return {"text": f"译文:{text}", "model": "fake", "elapsed_ms": 12}

    def get_clipboard_history_items(self):
        return [{"index": 0, "text": "alpha", "preview": "alpha"}]

    def select_clipboard_history_item(self, index: int):
        self.calls.append(f"clipboard:{index}")
        return {"index": 0, "text": "alpha", "preview": "alpha"}

    def reload_config(self) -> None:
        self.reloads += 1


@dataclass(slots=True)
class _ConfigSection:
    notifications_enabled: bool = True
    tray_display: str = "default"
    port: int = 7777


def test_runtime_api_returns_json_friendly_state_snapshot() -> None:
    api = RuntimeApi(_FakeApp())

    state = api.get_state()

    assert state["capture"] == {"enabled": True, "label": "capture"}
    assert state["clipboard_history"]["item_count"] == 2
    assert state["proxy"]["address"] == "http://127.0.0.1:7890"


def test_runtime_api_dispatches_named_actions() -> None:
    app = _FakeApp()
    api = RuntimeApi(app, events=RuntimeEventStore())

    api.dispatch_action("capture.screenshot_and_pin")

    assert app.calls == ["screenshot_and_pin"]
    assert api.get_events(limit=1)[0]["topic"] == "action.dispatched"


def test_runtime_api_rejects_unknown_actions() -> None:
    api = RuntimeApi(_FakeApp())

    with pytest.raises(KeyError):
        api.dispatch_action("missing.action")


def test_runtime_api_translates_text() -> None:
    app = _FakeApp()
    api = RuntimeApi(app, events=RuntimeEventStore())

    result = api.translate_text("hello")

    assert result == {"text": "译文:hello", "model": "fake", "elapsed_ms": 12}
    assert app.calls == ["translate:hello"]
    assert api.get_events(limit=1)[0]["topic"] == "translator.translated"


def test_runtime_api_exposes_clipboard_history() -> None:
    app = _FakeApp()
    api = RuntimeApi(app, events=RuntimeEventStore())

    assert api.get_clipboard_history()["items"][0]["text"] == "alpha"
    assert api.select_clipboard_history_item(0)["item"]["text"] == "alpha"
    assert app.calls == ["clipboard:0"]
    assert api.get_events(limit=1)[0]["topic"] == "clipboard.selected"


def test_runtime_api_reads_and_updates_config() -> None:
    app = _FakeApp()
    api = RuntimeApi(app, events=RuntimeEventStore())

    assert api.get_config()["general"]["tray_display"] == "default"

    updated = api.update_config({"general": {"notifications_enabled": False}, "subconverter": {"port": "8888"}})

    assert updated["general"]["notifications_enabled"] is False
    assert updated["subconverter"]["port"] == 8888
    assert app.config.general.notifications_enabled is False
    assert app.config.subconverter.port == 8888
    assert "config.save" in app.calls
    assert app.reloads == 1
    assert api.get_events(limit=1)[0]["topic"] == "config.updated"


def test_runtime_api_rejects_unknown_config_fields() -> None:
    api = RuntimeApi(_FakeApp())

    with pytest.raises(KeyError):
        api.update_config({"general": {"missing": True}})


def test_runtime_api_filters_events_by_id() -> None:
    api = RuntimeApi(_FakeApp(), events=RuntimeEventStore())

    first = api.events.add("first", "First")
    api.events.add("second", "Second")

    events = api.get_events(after_id=first.id)

    assert [event["topic"] for event in events] == ["second"]
