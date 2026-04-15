from __future__ import annotations

import os
import sys
from pathlib import Path

SYSTEM_DIST_PACKAGES = (
    Path("/usr/lib/python3/dist-packages"),
    Path("/usr/local/lib/python3/dist-packages"),
)


def configure_linux_tray_backend() -> None:
    """Prefer the AppIndicator backend when the host system provides it."""
    if sys.platform != "linux":
        return
    if os.environ.get("PYSTRAY_BACKEND"):
        return

    _inject_system_dist_packages()
    if _can_use_appindicator():
        os.environ["PYSTRAY_BACKEND"] = "appindicator"


def _inject_system_dist_packages() -> None:
    """Expose Debian/Ubuntu system packages to virtualenv Python when needed."""
    for path in SYSTEM_DIST_PACKAGES:
        raw_path = str(path)
        if path.exists() and raw_path not in sys.path:
            sys.path.append(raw_path)


def _can_use_appindicator() -> bool:
    """Check whether GTK 3 and an AppIndicator namespace are importable."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        if not Gtk.init_check()[0]:
            return False

        for namespace in ("AppIndicator3", "AyatanaAppIndicator3"):
            try:
                gi.require_version(namespace, "0.1")
                __import__(f"gi.repository.{namespace}")
                return True
            except Exception:
                continue
    except Exception:
        return False

    return False
