from __future__ import annotations

import io
import os
import subprocess
import shutil
import threading
from pathlib import Path

from PIL import Image

from ...log import get_logger
from ..base import ClipboardService, ScreenCaptureService

_logger = get_logger("capture")

PRIMARY = "primary"
CLIPBOARD = "clipboard"

def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or "WAYLAND_DISPLAY" in os.environ


def _background_copy(cmd: list[str], data: bytes) -> None:
    try:
        subprocess.run(cmd, input=data, check=True)
    except Exception as exc:
        _logger.warning("Background clipboard copy failed: %s", exc)


class LinuxScreenCaptureService(ScreenCaptureService):
    def __init__(self) -> None:
        try:
            import mss

            self._sct = mss.mss()
        except Exception:
            self._sct = None

    def grab_full_screen(self) -> Image.Image | None:
        if self._sct:
            try:
                shot = self._sct.grab(self._sct.monitors[0])
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


class LinuxClipboardService(ClipboardService):
    def copy_image_file(self, path: str) -> bool:
        if shutil.which("wl-copy") and _is_wayland():
            try:
                data = Path(path).read_bytes()
                threading.Thread(
                    target=_background_copy,
                    args=(["wl-copy", "-t", "image/png"], data),
                    daemon=True,
                ).start()
                return True
            except Exception:
                pass

        if shutil.which("xclip"):
            try:
                data = Path(path).read_bytes()
                threading.Thread(
                    target=_background_copy,
                    args=(["xclip", "-selection", "clipboard", "-t", "image/png", "-i"], data),
                    daemon=True,
                ).start()
                return True
            except Exception:
                pass

        return False

    def get_image(self) -> Image.Image | None:
        try:
            from PIL import ImageGrab

            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                return img
        except Exception:
            pass

        if shutil.which("xclip") and not _is_wayland():
            try:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout:
                    return Image.open(io.BytesIO(result.stdout))
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        if shutil.which("wl-paste") and _is_wayland():
            try:
                result = subprocess.run(
                    ["wl-paste", "-t", "image/png"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout:
                    return Image.open(io.BytesIO(result.stdout))
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        return None

    def read_text(self, source: str = CLIPBOARD) -> str | None:
        if shutil.which("wl-paste") and _is_wayland():
            try:
                args = ["wl-paste", "--no-newline"]
                if source == PRIMARY:
                    args.insert(1, "--primary")
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        if shutil.which("xclip"):
            try:
                selection = "primary" if source == PRIMARY else "clipboard"
                result = subprocess.run(
                    ["xclip", "-selection", selection, "-o"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        if shutil.which("xsel"):
            try:
                selection = "--primary" if source == PRIMARY else "--clipboard"
                result = subprocess.run(
                    ["xsel", selection, "--output"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        return None

    def write_text(self, text: str) -> bool:
        if shutil.which("wl-copy") and _is_wayland():
            try:
                result = subprocess.run(
                    ["wl-copy"],
                    input=text,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        if shutil.which("xclip"):
            try:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        if shutil.which("xsel"):
            try:
                result = subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        return False
