from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...app import DeskVaneApp


class HotkeyManager:
    """Global hotkey listener switching between platform backends automatically."""

    def __init__(self, app: DeskVaneApp) -> None:
        self.app = app
        self._backend = None
        self._bindings: dict[str, Callable] = {}

    def _init_backend(self) -> None:
        if self._backend is None:
            self._backend = self.app.platform_services.hotkey_backend_factory(self.app)

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback
        if self._backend is not None:
            self._backend.register(hotkey, callback)

    def start(self) -> None:
        self._init_backend()
        self._backend.clear()
        for hotkey, callback in self._bindings.items():
            self._backend.register(hotkey, callback)
        self._backend.start()

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.stop()

    def clear(self) -> None:
        self._bindings.clear()
        if self._backend is not None:
            self._backend.clear()

    def restart(self) -> None:
        self.stop()
        self.start()
