"""Screen capture helpers — multi-backend full-screen grab and clipboard copy."""

from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

try:
    import mss
    _SCT = mss.mss()
except Exception:
    _SCT = None


def _grab_full_screen() -> Image.Image | None:
    """Capture the full screen."""
    if _SCT:
        try:
            shot = _SCT.grab(_SCT.monitors[0])
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            pass
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["grim", "-"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Image.open(io.BytesIO(result.stdout))
    except Exception:
        pass
    return None


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or "WAYLAND_DISPLAY" in os.environ


def _background_copy(cmd: list[str], data: bytes) -> None:
    from .log import get_logger
    try:
        subprocess.run(cmd, input=data, check=True)
    except Exception as e:
        get_logger("screenshot").warning("Background clipboard copy failed: %s", e)


def _copy_image_to_clipboard(path: str) -> bool:
    """Copy an image file to the clipboard via xclip or wl-copy."""
    import shutil
    import threading

    if shutil.which("wl-copy") and _is_wayland():
        try:
            with open(path, "rb") as f:
                data = f.read()
            threading.Thread(
                target=_background_copy,
                args=(["wl-copy", "-t", "image/png"], data),
                daemon=True
            ).start()
            return True
        except Exception:
            pass

    if shutil.which("xclip"):
        try:
            with open(path, "rb") as f:
                data = f.read()
            threading.Thread(
                target=_background_copy,
                args=(["xclip", "-selection", "clipboard", "-t", "image/png", "-i"], data),
                daemon=True
            ).start()
            return True
        except Exception:
            pass

    return False


def _get_image_from_clipboard() -> Image.Image | None:
    """Read an image from the clipboard."""
    import shutil
    from PIL import ImageGrab
    try:
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            return img
    except Exception:
        pass

    if shutil.which("xclip") and not _is_wayland():
        try:
            result = subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"], capture_output=True, timeout=2)
            if result.returncode == 0 and result.stdout:
                return Image.open(io.BytesIO(result.stdout))
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    if shutil.which("wl-paste") and _is_wayland():
        try:
            result = subprocess.run(["wl-paste", "-t", "image/png"], capture_output=True, timeout=2)
            if result.returncode == 0 and result.stdout:
                return Image.open(io.BytesIO(result.stdout))
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    return None
