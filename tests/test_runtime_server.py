from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from deskvane.core.runtime_api import RuntimeApi
from deskvane.core.runtime_server import RuntimeHttpServer


@dataclass(frozen=True)
class _State:
    enabled: bool


class _FakeApp:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reloads = 0
        self.config = _Config(
            general=_ConfigSection(notifications_enabled=True, tray_display="default"),
            subconverter=_ConfigSection(port=7777),
        )
        self.config_manager = _ConfigManager(self)

    def get_capture_state(self):
        return _State(True)

    def get_clipboard_history_state(self):
        return _State(True)

    def get_translator_state(self):
        return _State(False)

    def get_shell_state(self):
        return _State(True)

    def get_proxy_state(self):
        return _State(False)

    def get_subconverter_state(self):
        return _State(True)

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


@dataclass(slots=True)
class _Config:
    general: _ConfigSection
    subconverter: _ConfigSection


class _ConfigManager:
    def __init__(self, app: _FakeApp) -> None:
        self.app = app

    def save(self, config) -> None:
        self.app.calls.append("config.save")


def _get_json(url: str):
    with urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _patch_json(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="PATCH", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _options(url: str):
    request = Request(url, method="OPTIONS")
    return urlopen(request, timeout=2)


def test_runtime_http_server_exposes_health_state_and_actions() -> None:
    app = _FakeApp()
    server = RuntimeHttpServer(RuntimeApi(app), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        assert _get_json(f"{server.base_url}/health") == {"status": "ok"}
        assert _get_json(f"{server.base_url}/state")["capture"] == {"enabled": True}
        assert _get_json(f"{server.base_url}/config")["general"]["tray_display"] == "default"
        assert _get_json(f"{server.base_url}/events") == {"events": []}
        assert "capture.screenshot_and_pin" in _get_json(f"{server.base_url}/actions")["actions"]

        assert _post_json(f"{server.base_url}/actions/capture.screenshot_and_pin", {}) == {"ok": True}
        assert app.calls == ["screenshot_and_pin"]
        assert _get_json(f"{server.base_url}/events")["events"][-1]["topic"] == "action.dispatched"
    finally:
        server.stop()


def test_runtime_http_server_updates_config() -> None:
    app = _FakeApp()
    server = RuntimeHttpServer(RuntimeApi(app), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        updated = _patch_json(
            f"{server.base_url}/config",
            {"general": {"tray_display": "gpu_mem"}, "subconverter": {"port": 8888}},
        )

        assert updated["general"]["tray_display"] == "gpu_mem"
        assert updated["subconverter"]["port"] == 8888
        assert app.config.general.tray_display == "gpu_mem"
        assert app.reloads == 1
        assert _get_json(f"{server.base_url}/events?limit=1")["events"][0]["topic"] == "config.updated"
    finally:
        server.stop()


def test_runtime_http_server_translates_text() -> None:
    app = _FakeApp()
    server = RuntimeHttpServer(RuntimeApi(app), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        result = _post_json(f"{server.base_url}/translator/translate", {"text": "hello"})

        assert result == {"text": "译文:hello", "model": "fake", "elapsed_ms": 12}
        assert app.calls == ["translate:hello"]
    finally:
        server.stop()


def test_runtime_http_server_exposes_clipboard_history() -> None:
    app = _FakeApp()
    server = RuntimeHttpServer(RuntimeApi(app), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        assert _get_json(f"{server.base_url}/clipboard/history")["items"][0]["text"] == "alpha"
        assert _post_json(f"{server.base_url}/clipboard/select", {"index": 0})["item"]["text"] == "alpha"
        assert app.calls == ["clipboard:0"]
    finally:
        server.stop()


def test_runtime_http_server_allows_browser_preflight() -> None:
    server = RuntimeHttpServer(RuntimeApi(_FakeApp()), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        with _options(f"{server.base_url}/config") as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "*"
            assert "PATCH" in response.headers["Access-Control-Allow-Methods"]
    finally:
        server.stop()


def test_runtime_http_server_returns_404_for_unknown_action() -> None:
    server = RuntimeHttpServer(RuntimeApi(_FakeApp()), port=0)
    server.start()
    if not server.is_running:
        pytest.skip("local socket binding is unavailable in this environment")
    try:
        try:
            _post_json(f"{server.base_url}/actions/missing.action", {})
        except HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("expected HTTP 404")
    finally:
        server.stop()
