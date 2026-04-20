from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest import mock

from deskvane.platform.factory import create_platform_services


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls = []

    def call_soon(self, callback) -> None:
        self.calls.append(callback)


def _fake_app(services):
    return SimpleNamespace(
        platform_services=services,
        dispatcher=_FakeDispatcher(),
        notifier=SimpleNamespace(show=lambda *args, **kwargs: None),
    )


def test_windows_platform_shell_services_smoke() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, \
         mock.patch.dict(os.environ, {"DESKVANE_WINDOWS_STARTUP_DIR": temp_dir}, clear=False), \
         mock.patch("deskvane.platform.factory.sys.platform", "win32"):
        services = create_platform_services()

        app = _fake_app(services)
        backend = services.hotkey_backend_factory(app)

        assert services.info.is_windows is True
        assert services.info.supports_tray_menu is True
        assert services.info.supports_hotkey_grab is True
        assert services.tray_adapter.build_label_setter() is None
        services.tray_adapter.bind_menu_observers(object(), lambda: None, lambda: None)
        assert services.autostart.enable("deskvane --minimized") is True
        assert services.autostart.is_enabled() is True
        assert services.autostart.disable() is True
        backend.clear()


def test_macos_platform_shell_services_smoke() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, \
         mock.patch.dict(os.environ, {"DESKVANE_MACOS_LAUNCH_AGENTS_DIR": temp_dir}, clear=False), \
         mock.patch("deskvane.platform.factory.sys.platform", "darwin"):
        services = create_platform_services()

        app = _fake_app(services)
        backend = services.hotkey_backend_factory(app)

        assert services.info.is_macos is True
        assert services.info.supports_tray_menu is True
        assert services.info.supports_hotkey_grab is True
        assert services.tray_adapter.build_label_setter() is None
        services.tray_adapter.bind_menu_observers(object(), lambda: None, lambda: None)
        assert services.autostart.enable("deskvane --minimized") is True
        assert services.autostart.is_enabled() is True
        assert services.autostart.disable() is True
        backend.clear()
