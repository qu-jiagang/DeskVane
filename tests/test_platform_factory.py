from __future__ import annotations

from unittest import mock

from deskvane.platform.base import PlatformInfo
import deskvane.platform.factory as platform_factory
from deskvane.platform.factory import DefaultOpenerService, create_platform_services
from deskvane.platform.macos.autostart import MacOSAutostartService
from deskvane.platform.macos.capture import MacOSClipboardService, MacOSScreenCaptureService
from deskvane.platform.macos.notification import MacOSNotificationService
from deskvane.platform.null import NullProxySessionService
from deskvane.platform.tray import MacOSTrayPlatformAdapter, WindowsTrayPlatformAdapter
from deskvane.platform.windows.autostart import WindowsAutostartService
from deskvane.platform.windows.capture import WindowsClipboardService, WindowsScreenCaptureService
from deskvane.platform.windows.notification import WindowsNotificationService


def test_create_platform_services_returns_linux_services_on_linux() -> None:
    with mock.patch("deskvane.platform.factory.sys.platform", "linux"):
        services = create_platform_services()

    assert services.info.is_linux is True
    assert services.info.supports_tray_menu is True
    assert services.info.supports_terminal_proxy is True
    assert services.info.supports_mihomo_party is True
    assert services.info.supports_hotkey_grab is True
    assert services.autostart.is_supported() is True
    assert services.autostart.is_enabled() is False
    assert services.opener is not None
    assert callable(services.hotkey_backend_factory)
    assert services.tray_adapter is not None
    assert callable(services.clipboard.read_text)
    assert callable(services.clipboard.write_text)


def test_create_platform_services_returns_windows_services_on_win32() -> None:
    with mock.patch("deskvane.platform.factory.sys.platform", "win32"):
        services = create_platform_services()

    assert services.info.is_windows is True
    assert services.info.supports_tray_menu is True
    assert services.info.supports_terminal_proxy is False
    assert services.info.supports_mihomo_party is False
    assert services.info.supports_hotkey_grab is True
    assert services.autostart.is_supported() is True
    assert services.autostart.is_enabled() is False
    assert services.proxy_session.is_enabled() is False
    assert services.opener is not None
    assert callable(services.hotkey_backend_factory)
    assert services.tray_adapter is not None
    assert callable(services.clipboard.read_text)
    assert callable(services.clipboard.write_text)
    assert isinstance(services.notification, WindowsNotificationService)
    assert isinstance(services.screen_capture, WindowsScreenCaptureService)
    assert isinstance(services.clipboard, WindowsClipboardService)
    assert isinstance(services.autostart, WindowsAutostartService)
    assert isinstance(services.proxy_session, NullProxySessionService)
    assert isinstance(services.tray_adapter, WindowsTrayPlatformAdapter)


def test_create_platform_services_returns_macos_services_on_darwin() -> None:
    with mock.patch("deskvane.platform.factory.sys.platform", "darwin"):
        services = create_platform_services()

    assert services.info.is_macos is True
    assert services.info.supports_tray_menu is True
    assert services.info.supports_terminal_proxy is False
    assert services.info.supports_mihomo_party is False
    assert services.info.supports_hotkey_grab is True
    assert services.autostart.is_supported() is True
    assert services.autostart.is_enabled() is False
    assert services.proxy_session.is_enabled() is False
    assert services.opener is not None
    assert callable(services.hotkey_backend_factory)
    assert isinstance(services.tray_adapter, MacOSTrayPlatformAdapter)
    assert callable(services.clipboard.read_text)
    assert callable(services.clipboard.write_text)
    assert isinstance(services.notification, MacOSNotificationService)
    assert isinstance(services.screen_capture, MacOSScreenCaptureService)
    assert isinstance(services.clipboard, MacOSClipboardService)
    assert isinstance(services.autostart, MacOSAutostartService)
    assert isinstance(services.proxy_session, NullProxySessionService)


def test_default_opener_service_uses_xdg_open_on_linux() -> None:
    service = DefaultOpenerService(PlatformInfo(name="linux", display_name="Linux", is_linux=True))

    with mock.patch.object(platform_factory.subprocess, "Popen") as popen:
        assert service.open_path("/tmp/deskvane-test") is True

    popen.assert_called_once_with(["xdg-open", "/tmp/deskvane-test"])


def test_default_opener_service_uses_startfile_on_windows() -> None:
    service = DefaultOpenerService(PlatformInfo(name="windows", display_name="Windows", is_windows=True))

    with mock.patch.object(platform_factory.os, "startfile", create=True) as startfile:
        assert service.open_path("C:/DeskVane/test") is True

    startfile.assert_called_once_with("C:/DeskVane/test")


def test_default_opener_service_uses_open_on_macos() -> None:
    service = DefaultOpenerService(PlatformInfo(name="macos", display_name="macOS", is_macos=True))

    with mock.patch.object(platform_factory.subprocess, "Popen") as popen:
        assert service.open_path("/tmp/deskvane-test") is True

    popen.assert_called_once_with(["open", "/tmp/deskvane-test"])
