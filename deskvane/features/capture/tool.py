"""Screenshot tool — region capture, pin, OCR, and interactive selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from ...platform import get_platform_services
from ...ui.pin import PinnedImage
from .controller import ScreenshotController
from .service import ScreenshotService

if TYPE_CHECKING:
    from ...app import DeskVaneApp


class ScreenshotTool:
    """Region screenshot: overlay -> select -> save & copy & optionally pin."""

    def __init__(self, app) -> None:
        self.app = app
        self._platform_services = getattr(app, "platform_services", None)
        if self._platform_services is None:
            self._platform_services = get_platform_services()
        self._service = ScreenshotService(self._platform_services)
        self._controller = ScreenshotController(self.app, lambda image, x, y: self._create_pinned_image(image, x, y), self._service)
        self._pinned_images = []

    def take_screenshot(self) -> None:
        self._controller.take_screenshot()

    def take_screenshot_and_pin(self) -> None:
        self._controller.take_screenshot_and_pin()

    def take_screenshot_interactive(self) -> None:
        self._controller.take_screenshot_interactive()

    def take_pure_ocr(self) -> None:
        self._controller.take_pure_ocr()

    def pin_clipboard(self) -> None:
        self._controller.pin_clipboard()

    def _create_pinned_image(self, image: Image.Image, x: int, y: int) -> None:
        pinned = PinnedImage(root=self.app.root, image=image, x=x, y=y, on_close=self._on_pinned_closed)
        self._pinned_images.append(pinned)

    def _on_pinned_closed(self, pinned: PinnedImage) -> None:
        if pinned in self._pinned_images:
            self._pinned_images.remove(pinned)
