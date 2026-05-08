"""UI-layer modules for DeskVane."""

from .help_doc import generate_help_html
from .overlay import SelectionOverlay
from .pin import PinnedImage
from .settings_panel import open_settings
from .tray import TrayController

__all__ = [
    "TrayController",
    "SelectionOverlay",
    "PinnedImage",
    "generate_help_html",
    "open_settings",
]
