"""Screenshot tool — region capture, pin, OCR, and interactive selection."""

from __future__ import annotations

import os
import time
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from .capture import (
    _copy_image_to_clipboard,
    _get_image_from_clipboard,
    _grab_full_screen,
)
from .overlay import SelectionOverlay
from .pin import PinnedImage

if TYPE_CHECKING:
    from .app import DeskVaneApp


class ScreenshotTool:
    """Region screenshot: overlay → select → save & copy & optionally pin."""

    def __init__(self, app) -> None:
        self.app = app
        self._pinned_images = []
        self._overlay_active = False

    def take_screenshot(self) -> None:
        self._start_overlay(pin=False, interactive=False)

    def take_screenshot_and_pin(self) -> None:
        self._start_overlay(pin=True, interactive=False)

    def take_screenshot_interactive(self) -> None:
        self._start_overlay(pin=False, interactive=True)

    def take_pure_ocr(self) -> None:
        if getattr(self, "_overlay_active", False):
            return
        self._overlay_active = True

        bg = _grab_full_screen()
        if bg is None:
            self._overlay_active = False
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("OCR失败", "无法捕获屏幕")
            return

        def _on_done_wrapper(region, action=None):
            self._overlay_active = False
            cropped = bg.crop(region)
            import io, base64
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            self.app.submit_ocr(f"[img_b64]{b64_str}")

        def _on_cancel_wrapper():
            self._overlay_active = False

        SelectionOverlay(
            background=bg,
            on_done=_on_done_wrapper,
            on_cancel=_on_cancel_wrapper,
            interactive=False
        )

    def pin_clipboard(self) -> None:
        img = _get_image_from_clipboard()
        if img is None:
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("固定失败", "剪贴板中没有图片数据")
            return

        screen_width = self.app.root.winfo_screenwidth()
        screen_height = self.app.root.winfo_screenheight()
        x = (screen_width - img.width) // 2
        y = (screen_height - img.height) // 2
        self._create_pinned_image(img, x, y)

    def _start_overlay(self, pin: bool, interactive: bool = False) -> None:
        if getattr(self, "_overlay_active", False):
            return
        self._overlay_active = True

        bg = _grab_full_screen()
        if bg is None:
            self._overlay_active = False
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("截图失败", "无法捕获屏幕")
            return

        def _on_done_wrapper(region, action=None):
            self._overlay_active = False
            force_save = (action == "save")
            force_pin = (action == "pin")
            force_copy = (action in ("done", "save", "pin"))
            final_pin = pin or force_pin
            self._finish(bg, region, pin=final_pin, force_save=force_save, force_copy=force_copy)

        def _on_cancel_wrapper():
            self._overlay_active = False

        SelectionOverlay(
            background=bg,
            on_done=_on_done_wrapper,
            on_cancel=_on_cancel_wrapper,
            interactive=interactive
        )

    def _finish(self, full_image, region, pin: bool, force_save: bool = False, force_copy: bool = False) -> None:
        cropped = full_image.crop(region)
        x1, y1, x2, y2 = region

        if pin:
            self._create_pinned_image(cropped, x1, y1)

        filepath = ""
        save_it = force_save or self.app.config.screenshot.save_to_disk
        copy_it = force_copy or self.app.config.screenshot.copy_to_clipboard

        if save_it:
            save_dir = Path(os.path.expanduser(self.app.config.screenshot.save_dir))
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{ts}.png"
            filepath = str(save_dir / filename)
            cropped.save(filepath, "PNG")

        success_copy = False
        if copy_it:
            if not filepath:
                fd, filepath = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                cropped.save(filepath, "PNG")
            success_copy = _copy_image_to_clipboard(filepath)

            if not save_it:
                def safe_remove(p=filepath):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass
                self.app.root.after(2000, safe_remove)

        if self.app.config.screenshot.notifications_enabled:
            # Notify on failing copy
            if copy_it and not success_copy:
                self.app.notifier.show("复制失败", "未能写入剪贴板。请确保系统已安装 xclip (X11) 或 wl-clipboard (Wayland)")
                return

            if pin:
                action = "截图已固定并复制" if copy_it else "截图已固定"
            else:
                action = "截图已保存" if save_it else "截图已复制"
            self.app.notifier.show(action, filepath if save_it else "")

    def _create_pinned_image(self, image: Image.Image, x: int, y: int) -> None:
        pinned = PinnedImage(
            root=self.app.root,
            image=image,
            x=x,
            y=y,
            on_close=self._on_pinned_closed
        )
        self._pinned_images.append(pinned)

    def _on_pinned_closed(self, pinned: PinnedImage) -> None:
        if pinned in self._pinned_images:
            self._pinned_images.remove(pinned)
