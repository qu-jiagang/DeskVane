from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from pathlib import Path

from PIL import Image

from ...platform import get_platform_services


class ScreenshotService:
    """Low-level screenshot helpers shared by the controller."""

    def __init__(self, platform_services=None) -> None:
        self._platform_services = platform_services or get_platform_services()

    def grab_full_screen(self) -> Image.Image | None:
        return self._platform_services.screen_capture.grab_full_screen()

    def get_clipboard_image(self) -> Image.Image | None:
        return self._platform_services.clipboard.get_image()

    def copy_image_file(self, path: str) -> bool:
        return self._platform_services.clipboard.copy_image_file(path)

    @staticmethod
    def crop_image(full_image: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
        return full_image.crop(region)

    @staticmethod
    def build_ocr_payload(image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return "[img_b64]" + base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def center_image(
        screen_width: int,
        screen_height: int,
        image_width: int,
        image_height: int,
    ) -> tuple[int, int]:
        x = (screen_width - image_width) // 2
        y = (screen_height - image_height) // 2
        return x, y

    @staticmethod
    def save_image(image: Image.Image, save_dir: str, filename: str | None = None) -> str:
        target_dir = Path(os.path.expanduser(save_dir))
        target_dir.mkdir(parents=True, exist_ok=True)
        name = filename or f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        filepath = target_dir / name
        image.save(filepath, "PNG")
        return str(filepath)

    @staticmethod
    def save_temp_image(image: Image.Image) -> str:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        image.save(path, "PNG")
        return path
