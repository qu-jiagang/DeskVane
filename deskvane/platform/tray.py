from __future__ import annotations

from collections.abc import Callable
import sys

from ..log import get_logger
from .base import TrayPlatformAdapter

_logger = get_logger("tray")


class NullTrayPlatformAdapter(TrayPlatformAdapter):
    def build_label_setter(self):
        return None

    def bind_menu_observers(self, icon, on_open: Callable[[], None], on_close: Callable[[], None]) -> None:
        return None


class WindowsTrayPlatformAdapter(TrayPlatformAdapter):
    def build_label_setter(self):
        return None

    def bind_menu_observers(self, icon, on_open: Callable[[], None], on_close: Callable[[], None]) -> None:
        return None


class MacOSTrayPlatformAdapter(TrayPlatformAdapter):
    def build_label_setter(self):
        return None

    def bind_menu_observers(self, icon, on_open: Callable[[], None], on_close: Callable[[], None]) -> None:
        return None


class LinuxTrayPlatformAdapter(TrayPlatformAdapter):
    def __init__(self) -> None:
        self._gtk_menu_type = None
        self._observed_menu_handle = None

    def build_label_setter(self):
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import GObject, Gtk
        except Exception:
            return None

        self._gtk_menu_type = Gtk.Menu

        def setter(indicator, label: str, guide: str) -> None:
            def callback():
                try:
                    indicator.set_label(label, guide)
                except Exception as exc:
                    _logger.debug("tray label refresh failed: %s", exc)
                return False

            GObject.idle_add(callback)

        return setter

    def bind_menu_observers(self, icon, on_open: Callable[[], None], on_close: Callable[[], None]) -> None:
        menu_handle = getattr(icon, "_menu_handle", None)
        gtk_menu_type = self._gtk_menu_type
        if menu_handle is None or gtk_menu_type is None:
            return
        if menu_handle is self._observed_menu_handle:
            return
        if not isinstance(menu_handle, gtk_menu_type):
            return

        def _on_show(*_args) -> None:
            on_open()

        def _on_hide(*_args) -> None:
            on_close()

        for signal_name, handler in (
            ("show", _on_show),
            ("hide", _on_hide),
            ("selection-done", _on_hide),
            ("deactivate", _on_hide),
        ):
            try:
                menu_handle.connect(signal_name, handler)
            except Exception:
                continue

        self._observed_menu_handle = menu_handle


def create_tray_platform_adapter() -> TrayPlatformAdapter:
    if sys.platform == "win32":
        return WindowsTrayPlatformAdapter()
    if sys.platform == "darwin":
        return MacOSTrayPlatformAdapter()
    if sys.platform != "linux":
        return NullTrayPlatformAdapter()
    return LinuxTrayPlatformAdapter()
