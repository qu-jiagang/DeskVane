from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from PIL import Image

from deskvane.features.capture.controller import ScreenshotController
from deskvane.features.capture.service import ScreenshotService


class _FakeOverlay:
    last_kwargs = None

    def __init__(self, **kwargs) -> None:
        _FakeOverlay.last_kwargs = kwargs


def _make_app(tmp_path, *, save_to_disk=False, copy_to_clipboard=True, notifications_enabled=True):
    notifier = SimpleNamespace(show=mock.Mock())
    root = SimpleNamespace(
        winfo_screenwidth=lambda: 100,
        winfo_screenheight=lambda: 80,
        after=mock.Mock(),
    )
    config = SimpleNamespace(
        screenshot=SimpleNamespace(
            notifications_enabled=notifications_enabled,
            save_to_disk=save_to_disk,
            copy_to_clipboard=copy_to_clipboard,
            save_dir=str(tmp_path / "shots"),
        )
    )
    return SimpleNamespace(root=root, config=config, notifier=notifier, submit_ocr=mock.Mock())


def test_screenshot_controller_saves_and_copies_interactive_selection(tmp_path, monkeypatch) -> None:
    image = Image.new("RGB", (10, 8), "white")
    saved_paths: list[str] = []
    copied_paths: list[str] = []
    create_pins: list[tuple[Image.Image, int, int]] = []
    service = SimpleNamespace(
        grab_full_screen=mock.Mock(return_value=image),
        get_clipboard_image=mock.Mock(return_value=None),
        copy_image_file=mock.Mock(side_effect=lambda path: copied_paths.append(path) or True),
        crop_image=mock.Mock(side_effect=lambda img, region: img.crop(region)),
        save_image=mock.Mock(side_effect=lambda img, save_dir: saved_paths.append(save_dir) or str(tmp_path / "shots" / "screenshot.png")),
        save_temp_image=mock.Mock(),
        build_ocr_payload=mock.Mock(),
        center_image=mock.Mock(),
    )
    app = _make_app(tmp_path, save_to_disk=False, copy_to_clipboard=False)

    monkeypatch.setattr("deskvane.features.capture.controller.SelectionOverlay", _FakeOverlay)
    controller = ScreenshotController(app, lambda img, x, y: create_pins.append((img, x, y)), ScreenshotService())
    controller._service = service

    controller.take_screenshot_interactive()
    overlay = _FakeOverlay.last_kwargs
    assert overlay["interactive"] is True

    overlay["on_done"]((1, 2, 5, 6), "save")

    assert saved_paths == [str(tmp_path / "shots")]
    assert copied_paths == [str(tmp_path / "shots" / "screenshot.png")]
    app.notifier.show.assert_called_once_with("截图已保存", str(tmp_path / "shots" / "screenshot.png"))
    assert create_pins == []


def test_screenshot_controller_copies_without_save_and_schedules_cleanup(tmp_path, monkeypatch) -> None:
    image = Image.new("RGB", (10, 8), "white")
    temp_file = tmp_path / "temp.png"
    temp_file.write_bytes(b"png")
    cleanup_calls: list[str] = []
    service = SimpleNamespace(
        grab_full_screen=mock.Mock(return_value=image),
        get_clipboard_image=mock.Mock(return_value=None),
        copy_image_file=mock.Mock(return_value=True),
        crop_image=mock.Mock(side_effect=lambda img, region: img.crop(region)),
        save_image=mock.Mock(),
        save_temp_image=mock.Mock(return_value=str(temp_file)),
        build_ocr_payload=mock.Mock(),
        center_image=mock.Mock(),
    )
    app = _make_app(tmp_path, save_to_disk=False, copy_to_clipboard=True)
    app.root.after.side_effect = lambda delay, callback: cleanup_calls.append(callback())

    monkeypatch.setattr("deskvane.features.capture.controller.SelectionOverlay", _FakeOverlay)
    controller = ScreenshotController(app, lambda img, x, y: None, ScreenshotService())
    controller._service = service

    controller.take_screenshot()
    overlay = _FakeOverlay.last_kwargs
    overlay["on_done"]((1, 2, 5, 6), None)

    service.save_image.assert_not_called()
    service.save_temp_image.assert_called_once()
    service.copy_image_file.assert_called_once_with(str(temp_file))
    assert cleanup_calls == [None]
    app.notifier.show.assert_called_once_with("截图已复制", "")


def test_screenshot_controller_pins_clipboard_centered(tmp_path) -> None:
    image = Image.new("RGB", (10, 8), "white")
    create_pins: list[tuple[Image.Image, int, int]] = []
    service = SimpleNamespace(
        grab_full_screen=mock.Mock(return_value=None),
        get_clipboard_image=mock.Mock(return_value=image),
        copy_image_file=mock.Mock(),
        crop_image=mock.Mock(),
        save_image=mock.Mock(),
        save_temp_image=mock.Mock(),
        build_ocr_payload=mock.Mock(),
        center_image=mock.Mock(return_value=(45, 36)),
    )
    app = _make_app(tmp_path)
    controller = ScreenshotController(app, lambda img, x, y: create_pins.append((img, x, y)), ScreenshotService())
    controller._service = service

    controller.pin_clipboard()

    assert create_pins == [(image, 45, 36)]
    service.get_clipboard_image.assert_called_once()


def test_screenshot_controller_builds_pure_ocr_payload(monkeypatch, tmp_path) -> None:
    image = Image.new("RGB", (6, 4), "white")
    service = SimpleNamespace(
        grab_full_screen=mock.Mock(return_value=image),
        get_clipboard_image=mock.Mock(),
        copy_image_file=mock.Mock(),
        crop_image=mock.Mock(side_effect=lambda img, region: img.crop(region)),
        save_image=mock.Mock(),
        save_temp_image=mock.Mock(),
        build_ocr_payload=mock.Mock(return_value="[img_b64]payload"),
        center_image=mock.Mock(),
    )
    app = _make_app(tmp_path)
    monkeypatch.setattr("deskvane.features.capture.controller.SelectionOverlay", _FakeOverlay)
    controller = ScreenshotController(app, lambda img, x, y: None, ScreenshotService())
    controller._service = service

    controller.take_pure_ocr()
    overlay = _FakeOverlay.last_kwargs
    overlay["on_done"]((0, 0, 3, 3), None)

    service.build_ocr_payload.assert_called_once()
    app.submit_ocr.assert_called_once_with("[img_b64]payload")
