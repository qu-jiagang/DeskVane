from __future__ import annotations

from unittest import mock

from deskvane.platform import tray as platform_tray


def test_create_tray_platform_adapter_returns_noop_on_non_linux() -> None:
    with mock.patch.object(platform_tray.sys, "platform", "win32"):
        adapter = platform_tray.create_tray_platform_adapter()

    assert isinstance(adapter, platform_tray.WindowsTrayPlatformAdapter)
    assert adapter.build_label_setter() is None
    adapter.bind_menu_observers(object(), lambda: None, lambda: None)


def test_create_tray_platform_adapter_returns_macos_adapter() -> None:
    with mock.patch.object(platform_tray.sys, "platform", "darwin"):
        adapter = platform_tray.create_tray_platform_adapter()

    assert isinstance(adapter, platform_tray.MacOSTrayPlatformAdapter)
    assert adapter.build_label_setter() is None
    adapter.bind_menu_observers(object(), lambda: None, lambda: None)


def test_linux_tray_platform_adapter_build_label_setter_handles_missing_gi() -> None:
    adapter = platform_tray.LinuxTrayPlatformAdapter()

    with mock.patch.dict("sys.modules", {"gi": None}):
        label_setter = adapter.build_label_setter()

    assert label_setter is None
