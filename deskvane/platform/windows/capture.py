from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from ..base import ClipboardService, ScreenCaptureService


class WindowsScreenCaptureService(ScreenCaptureService):
    def grab_full_screen(self) -> Image.Image | None:
        try:
            from PIL import ImageGrab

            return ImageGrab.grab(all_screens=True)
        except Exception:
            pass
        try:
            from PIL import ImageGrab

            return ImageGrab.grab()
        except Exception:
            return None


class WindowsClipboardService(ClipboardService):
    def copy_image_file(self, path: str) -> bool:
        escaped_path = str(Path(path)).replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            f"$img = [System.Drawing.Image]::FromFile('{escaped_path}');"
            "[System.Windows.Forms.Clipboard]::SetImage($img);"
            "$img.Dispose()"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
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
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                timeout=3,
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
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
                input=text,
                text=True,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False
