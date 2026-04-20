from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


class NotificationService(ABC):
    @abstractmethod
    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        raise NotImplementedError


class ScreenCaptureService(ABC):
    @abstractmethod
    def grab_full_screen(self) -> Image.Image | None:
        raise NotImplementedError


class ClipboardService(ABC):
    @abstractmethod
    def copy_image_file(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_image(self) -> Image.Image | None:
        raise NotImplementedError

    @abstractmethod
    def read_text(self, source: str = "clipboard") -> str | None:
        raise NotImplementedError

    @abstractmethod
    def write_text(self, text: str) -> bool:
        raise NotImplementedError


class OpenerService(ABC):
    @abstractmethod
    def open_path(self, path: str | Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def open_uri(self, uri: str) -> bool:
        raise NotImplementedError


class HotkeyBackend(ABC):
    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def register(self, hotkey: str, callback: Callable[..., Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class TrayPlatformAdapter(ABC):
    @abstractmethod
    def build_label_setter(self):
        raise NotImplementedError

    @abstractmethod
    def bind_menu_observers(
        self,
        icon: Any,
        on_open: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        raise NotImplementedError


class AutostartService(ABC):
    @abstractmethod
    def is_supported(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_enabled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def enable(self, command: str | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disable(self) -> bool:
        raise NotImplementedError


class ProxySessionService(ABC):
    @abstractmethod
    def setup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_enabled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def enable(self, address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def disable(self, address: str | None = None) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class PlatformInfo:
    name: str
    display_name: str
    is_linux: bool = False
    is_windows: bool = False
    is_macos: bool = False
    supports_tray_menu: bool = False
    supports_terminal_proxy: bool = False
    supports_mihomo_party: bool = False
    supports_hotkey_grab: bool = False


@dataclass(slots=True)
class PlatformServices:
    info: PlatformInfo
    notification: NotificationService
    screen_capture: ScreenCaptureService
    clipboard: ClipboardService
    opener: OpenerService
    autostart: AutostartService
    proxy_session: ProxySessionService
    hotkey_backend_factory: Callable[[Any], HotkeyBackend]
    tray_adapter: TrayPlatformAdapter
