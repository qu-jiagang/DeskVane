"""DeskVane — Linux tray-based aggregation toolbox."""

from .version import get_version

__version__ = get_version()

__all__ = ["__version__", "ui_theme"]


def __getattr__(name: str):
    if name == "ui_theme":
        from .ui import ui_theme

        return ui_theme
    raise AttributeError(name)
