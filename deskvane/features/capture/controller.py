from __future__ import annotations

import os

from ...ui.overlay import SelectionOverlay
from .service import ScreenshotService


class ScreenshotController:
    """Orchestrates screenshot flows and keeps ScreenshotTool thin."""

    def __init__(self, app, create_pinned_image, service: ScreenshotService | None = None) -> None:
        self.app = app
        self._create_pinned_image = create_pinned_image
        self._service = service or ScreenshotService(getattr(app, "platform_services", None))
        self._overlay_active = False

    def take_screenshot(self) -> None:
        self._start_overlay(pin=False, interactive=False)

    def take_screenshot_and_pin(self) -> None:
        self._start_overlay(pin=True, interactive=False)

    def take_screenshot_interactive(self) -> None:
        self._start_overlay(pin=False, interactive=True)

    def take_pure_ocr(self) -> None:
        if self._overlay_active:
            return
        self._overlay_active = True

        bg = self._service.grab_full_screen()
        if bg is None:
            self._overlay_active = False
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("OCR失败", "无法捕获屏幕")
            return

        def _on_done_wrapper(region, action=None):
            self._overlay_active = False
            payload = self._service.build_ocr_payload(self._service.crop_image(bg, region))
            self.app.submit_ocr(payload)

        def _on_cancel_wrapper():
            self._overlay_active = False

        SelectionOverlay(background=bg, on_done=_on_done_wrapper, on_cancel=_on_cancel_wrapper, interactive=False)

    def pin_clipboard(self) -> None:
        img = self._service.get_clipboard_image()
        if img is None:
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("固定失败", "剪贴板中没有图片数据")
            return

        screen_width = self.app.root.winfo_screenwidth()
        screen_height = self.app.root.winfo_screenheight()
        x, y = self._service.center_image(screen_width, screen_height, img.width, img.height)
        self._create_pinned_image(img, x, y)

    def _start_overlay(self, pin: bool, interactive: bool = False) -> None:
        if self._overlay_active:
            return
        self._overlay_active = True

        bg = self._service.grab_full_screen()
        if bg is None:
            self._overlay_active = False
            if self.app.config.screenshot.notifications_enabled:
                self.app.notifier.show("截图失败", "无法捕获屏幕")
            return

        def _on_done_wrapper(region, action=None):
            self._overlay_active = False
            force_save = action == "save"
            force_pin = action == "pin"
            force_copy = action in ("done", "save", "pin")
            self._finish(bg, region, pin=pin or force_pin, force_save=force_save, force_copy=force_copy)

        def _on_cancel_wrapper():
            self._overlay_active = False

        SelectionOverlay(background=bg, on_done=_on_done_wrapper, on_cancel=_on_cancel_wrapper, interactive=interactive)

    def _finish(self, full_image, region, pin: bool, force_save: bool = False, force_copy: bool = False) -> None:
        cropped = self._service.crop_image(full_image, region)
        x1, y1, _, _ = region

        if pin:
            self._create_pinned_image(cropped, x1, y1)

        filepath = ""
        save_it = force_save or self.app.config.screenshot.save_to_disk
        copy_it = force_copy or self.app.config.screenshot.copy_to_clipboard

        if save_it:
            filepath = self._service.save_image(cropped, self.app.config.screenshot.save_dir)

        success_copy = False
        if copy_it:
            if not filepath:
                filepath = self._service.save_temp_image(cropped)
            success_copy = self._service.copy_image_file(filepath)

            if not save_it:
                def safe_remove(p=filepath):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass

                self.app.root.after(2000, safe_remove)

        if self.app.config.screenshot.notifications_enabled:
            if copy_it and not success_copy:
                self.app.notifier.show("复制失败", "未能写入剪贴板。请确保系统已安装 xclip (X11) 或 wl-clipboard (Wayland)")
                return

            if pin:
                action = "截图已固定并复制" if copy_it else "截图已固定"
            else:
                action = "截图已保存" if save_it else "截图已复制"
            self.app.notifier.show(action, filepath if save_it else "")
