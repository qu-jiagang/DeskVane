from __future__ import annotations

import os
import sys
import subprocess
import webbrowser
from functools import lru_cache
from pathlib import Path

from .base import OpenerService, PlatformInfo, PlatformServices
from .linux.autostart import LinuxAutostartService
from .linux.capture import LinuxClipboardService, LinuxScreenCaptureService
from .linux.notification import LinuxNotificationService
from .linux.proxy_session import LinuxProxySessionService
from .macos.autostart import MacOSAutostartService
from .macos.capture import MacOSClipboardService, MacOSScreenCaptureService
from .macos.notification import MacOSNotificationService
from .hotkeys import create_hotkey_backend
from .tray import MacOSTrayPlatformAdapter, WindowsTrayPlatformAdapter, create_tray_platform_adapter
from .null import (
    NullAutostartService,
    NullClipboardService,
    NullHotkeyBackend,
    NullNotificationService,
    NullProxySessionService,
    NullScreenCaptureService,
    NullTrayPlatformAdapter,
)
from .windows.autostart import WindowsAutostartService
from .windows.capture import WindowsClipboardService, WindowsScreenCaptureService
from .windows.notification import WindowsNotificationService


class DefaultOpenerService(OpenerService):
    def __init__(self, info: PlatformInfo) -> None:
        self._info = info

    def open_path(self, path: str | Path) -> bool:
        return self._open_target(str(Path(path)))

    def open_uri(self, uri: str) -> bool:
        try:
            if webbrowser.open(uri):
                return True
        except Exception:
            pass
        return self._open_target(uri)

    def _open_target(self, target: str) -> bool:
        try:
            if self._info.is_windows:
                os.startfile(target)
                return True
            if self._info.is_macos:
                subprocess.Popen(["open", target])
                return True
            subprocess.Popen(["xdg-open", target])
            return True
        except (AttributeError, FileNotFoundError, OSError):
            return False


def _platform_info() -> PlatformInfo:
    if sys.platform.startswith("linux"):
        return PlatformInfo(
            name="linux",
            display_name="Linux",
            is_linux=True,
            supports_tray_menu=True,
            supports_terminal_proxy=True,
            supports_mihomo_party=True,
            supports_hotkey_grab=True,
        )
    if sys.platform == "win32":
        return PlatformInfo(
            name="windows",
            display_name="Windows",
            is_windows=True,
            supports_tray_menu=True,
            supports_hotkey_grab=True,
        )
    if sys.platform == "darwin":
        return PlatformInfo(
            name="macos",
            display_name="macOS",
            is_macos=True,
            supports_tray_menu=True,
            supports_hotkey_grab=True,
        )
    return PlatformInfo(name=sys.platform, display_name=sys.platform)


def create_platform_services() -> PlatformServices:
    info = _platform_info()
    if info.is_linux:
        return PlatformServices(
            info=info,
            notification=LinuxNotificationService(),
            screen_capture=LinuxScreenCaptureService(),
            clipboard=LinuxClipboardService(),
            opener=DefaultOpenerService(info),
            autostart=LinuxAutostartService(),
            proxy_session=LinuxProxySessionService(),
            hotkey_backend_factory=create_hotkey_backend,
            tray_adapter=create_tray_platform_adapter(),
        )
    if info.is_windows:
        return PlatformServices(
            info=info,
            notification=WindowsNotificationService(),
            screen_capture=WindowsScreenCaptureService(),
            clipboard=WindowsClipboardService(),
            opener=DefaultOpenerService(info),
            autostart=WindowsAutostartService(),
            proxy_session=NullProxySessionService(),
            hotkey_backend_factory=create_hotkey_backend,
            tray_adapter=WindowsTrayPlatformAdapter(),
        )
    if info.is_macos:
        return PlatformServices(
            info=info,
            notification=MacOSNotificationService(),
            screen_capture=MacOSScreenCaptureService(),
            clipboard=MacOSClipboardService(),
            opener=DefaultOpenerService(info),
            autostart=MacOSAutostartService(),
            proxy_session=NullProxySessionService(),
            hotkey_backend_factory=create_hotkey_backend,
            tray_adapter=MacOSTrayPlatformAdapter(),
        )
    return PlatformServices(
        info=info,
        notification=NullNotificationService(),
        screen_capture=NullScreenCaptureService(),
        clipboard=NullClipboardService(),
        opener=DefaultOpenerService(info),
        autostart=NullAutostartService(),
        proxy_session=NullProxySessionService(),
        hotkey_backend_factory=lambda app: NullHotkeyBackend(),
        tray_adapter=NullTrayPlatformAdapter(),
    )


@lru_cache(maxsize=1)
def get_platform_services() -> PlatformServices:
    return create_platform_services()
