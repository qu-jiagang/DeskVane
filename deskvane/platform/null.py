from __future__ import annotations

from pathlib import Path

from PIL import Image

from .base import (
    AutostartService,
    ClipboardService,
    HotkeyBackend,
    NotificationService,
    OpenerService,
    ProxySessionService,
    ScreenCaptureService,
    TrayPlatformAdapter,
)


class NullNotificationService(NotificationService):
    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        return None


class NullScreenCaptureService(ScreenCaptureService):
    def grab_full_screen(self) -> Image.Image | None:
        return None


class NullClipboardService(ClipboardService):
    def copy_image_file(self, path: str) -> bool:
        return False

    def get_image(self) -> Image.Image | None:
        return None

    def read_text(self, source: str = "clipboard") -> str | None:
        return None

    def write_text(self, text: str) -> bool:
        return False


class NullOpenerService(OpenerService):
    def open_path(self, path: str | Path) -> bool:
        return False

    def open_uri(self, uri: str) -> bool:
        return False


class NullAutostartService(AutostartService):
    def is_supported(self) -> bool:
        return False

    def is_enabled(self) -> bool:
        return False

    def enable(self, command: str | None = None) -> bool:
        return False

    def disable(self) -> bool:
        return False


class NullProxySessionService(ProxySessionService):
    def setup(self) -> None:
        return None

    def is_enabled(self) -> bool:
        return False

    def enable(self, address: str) -> None:
        return None

    def disable(self, address: str | None = None) -> None:
        return None


class NullHotkeyBackend(HotkeyBackend):
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def register(self, hotkey: str, callback) -> None:
        return None

    def clear(self) -> None:
        return None


class NullTrayPlatformAdapter(TrayPlatformAdapter):
    def build_label_setter(self):
        return None

    def bind_menu_observers(self, icon, on_open, on_close) -> None:
        return None
