from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .core import ConfigManager, TaskManager
from .platform.base import PlatformServices

if TYPE_CHECKING:
    from .app import DeskVaneApp


@dataclass(slots=True)
class ModuleContext:
    platform: PlatformServices
    config: ConfigManager
    tasks: TaskManager
    app: DeskVaneApp
    ui_dispatcher: Any
    hotkey_registry: Any | None = None
    settings_registry: Any | None = None
    tray_registry: Any | None = None
