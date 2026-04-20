from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from deskvane.features.shell.hotkeys import HotkeyManager
from deskvane.platform import hotkeys as platform_hotkeys


class _FakeBackend:
    def __init__(self, app) -> None:
        self.app = app
        self.registered = []
        self.started = False
        self.stopped = False
        self.cleared = False

    def register(self, hotkey, callback) -> None:
        self.registered.append((hotkey, callback))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def clear(self) -> None:
        self.cleared = True


def test_hotkey_manager_delegates_backend_creation() -> None:
    app = SimpleNamespace(platform_services=SimpleNamespace(hotkey_backend_factory=mock.Mock()))
    backend = _FakeBackend(app)
    app.platform_services.hotkey_backend_factory.return_value = backend

    manager = HotkeyManager(app)
    manager.register("<ctrl>+a", lambda: None)
    manager.start()

    app.platform_services.hotkey_backend_factory.assert_called_once_with(app)
    assert backend.cleared is True
    assert backend.started is True
    assert backend.registered[0][0] == "<ctrl>+a"


def test_create_hotkey_backend_uses_pynput_on_non_linux() -> None:
    app = SimpleNamespace()
    sentinel = object()

    with mock.patch.object(platform_hotkeys.sys, "platform", "win32"), \
         mock.patch.object(platform_hotkeys, "WindowsHotkeyBackend", return_value=sentinel) as windows_mock, \
         mock.patch.object(platform_hotkeys, "PynputBackend") as pynput_mock, \
         mock.patch.object(platform_hotkeys, "X11Backend") as x11_mock, \
         mock.patch.object(platform_hotkeys, "KeyboardBackend") as keyboard_mock:
        backend = platform_hotkeys.create_hotkey_backend(app)

    assert backend is sentinel
    windows_mock.assert_called_once_with(app)
    pynput_mock.assert_not_called()
    x11_mock.assert_not_called()
    keyboard_mock.assert_not_called()


def test_windows_hotkey_backend_parses_common_hotkeys() -> None:
    parsed = platform_hotkeys.WindowsHotkeyBackend._parse_hotkey("<ctrl>+<alt>+h")

    assert parsed == (
        platform_hotkeys.WindowsHotkeyBackend.MOD_CONTROL | platform_hotkeys.WindowsHotkeyBackend.MOD_ALT,
        ord("H"),
    )


def test_create_hotkey_backend_uses_macos_backend_on_darwin() -> None:
    app = SimpleNamespace()
    sentinel = object()

    with mock.patch.object(platform_hotkeys.sys, "platform", "darwin"), \
         mock.patch.object(platform_hotkeys, "MacOSHotkeyBackend", return_value=sentinel) as macos_mock, \
         mock.patch.object(platform_hotkeys, "PynputBackend") as pynput_mock:
        backend = platform_hotkeys.create_hotkey_backend(app)

    assert backend is sentinel
    macos_mock.assert_called_once_with(app)
    pynput_mock.assert_not_called()
