from __future__ import annotations

from abc import ABC, abstractmethod

from .app_context import ModuleContext
from .core.contributions import HotkeySpec, SettingsSectionSpec, TraySectionContribution


class FeatureModule(ABC):
    name: str

    @abstractmethod
    def register(self, context: ModuleContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    def contribute_hotkeys(self) -> tuple[HotkeySpec, ...]:
        return ()

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return ()

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return ()
