from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from ..base import ClipboardService, ScreenCaptureService


class MacOSScreenCaptureService(ScreenCaptureService):
    def grab_full_screen(self) -> Image.Image | None:
        try:
            from PIL import ImageGrab

            return ImageGrab.grab()
        except Exception:
            return None


class MacOSClipboardService(ClipboardService):
    def copy_image_file(self, path: str) -> bool:
        script = (
            'set the clipboard to (read (POSIX file "{}") as PNG picture)'.format(
                str(Path(path)).replace('"', '\\"')
            )
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_image(self) -> Image.Image | None:
        try:
            from PIL import ImageGrab

            image = ImageGrab.grabclipboard()
            if isinstance(image, Image.Image):
                return image
        except Exception:
            pass
        return None

    def read_text(self, source: str = "clipboard") -> str | None:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return None

    def write_text(self, text: str) -> bool:
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                timeout=2,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False
