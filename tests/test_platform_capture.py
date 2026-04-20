from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import mock

from PIL import Image

import deskvane.platform as platform_services_module
from deskvane.platform.base import PlatformServices
from deskvane.platform.linux.capture import LinuxClipboardService, LinuxScreenCaptureService
from deskvane.features.capture.tool import ScreenshotTool


def test_capture_wrappers_delegate_to_platform_services() -> None:
    sent_image = Image.new("RGB", (2, 2), "white")
    fake_services = SimpleNamespace(
        screen_capture=SimpleNamespace(grab_full_screen=mock.Mock(return_value=sent_image)),
        clipboard=SimpleNamespace(
            copy_image_file=mock.Mock(return_value=True),
            get_image=mock.Mock(return_value=sent_image),
            read_text=mock.Mock(return_value="hello"),
            write_text=mock.Mock(return_value=True),
        ),
    )

    with mock.patch("deskvane.platform.get_platform_services", return_value=fake_services):
        services = platform_services_module.get_platform_services()
        assert services.screen_capture.grab_full_screen() is sent_image
        assert services.clipboard.copy_image_file("x.png") is True
        assert services.clipboard.get_image() is sent_image


def test_linux_screen_capture_prefers_mss() -> None:
    shot = SimpleNamespace(size=(3, 2), bgra=b"\xff\x00\x00\xff" * 6)
    fake_sct = SimpleNamespace(monitors=[object()], grab=mock.Mock(return_value=shot))
    fake_mss = SimpleNamespace(mss=mock.Mock(return_value=fake_sct))

    with mock.patch.dict(sys.modules, {"mss": fake_mss}):
        service = LinuxScreenCaptureService()

    image = service.grab_full_screen()

    assert image is not None
    assert image.size == (3, 2)
    fake_sct.grab.assert_called_once()


def test_linux_clipboard_copy_uses_wayland_backend(tmp_path, monkeypatch) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"png")
    service = LinuxClipboardService()
    calls: list[tuple[list[str], bytes]] = []

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr("deskvane.platform.linux.capture.shutil.which", lambda name: "/usr/bin/" + name if name == "wl-copy" else None)
    monkeypatch.setattr(
        "deskvane.platform.linux.capture.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: calls.append((args[0], args[1]))),
    )
    monkeypatch.setattr("deskvane.platform.linux.capture.subprocess.run", mock.Mock(return_value=SimpleNamespace(returncode=0)))

    assert service.copy_image_file(str(path)) is True
    assert calls == [(["wl-copy", "-t", "image/png"], b"png")]


def test_linux_clipboard_text_roundtrip_uses_wayland_backend(monkeypatch) -> None:
    service = LinuxClipboardService()

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr(
        "deskvane.platform.linux.capture.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"wl-paste", "wl-copy"} else None,
    )
    run_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        run_calls.append((args, kwargs))
        if args[0] == "wl-paste":
            return SimpleNamespace(returncode=0, stdout="hello")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("deskvane.platform.linux.capture.subprocess.run", fake_run)

    assert service.write_text("world") is True
    assert service.read_text("clipboard") == "hello"
    assert run_calls[0][0] == ["wl-copy"]
    assert run_calls[1][0] == ["wl-paste", "--no-newline"]


def test_screenshot_tool_uses_platform_services(monkeypatch) -> None:
    image = Image.new("RGB", (10, 8), "white")
    fake_services = PlatformServices(
        info=SimpleNamespace(name="linux", display_name="Linux", is_linux=True),
        notification=SimpleNamespace(show=mock.Mock()),
        screen_capture=SimpleNamespace(grab_full_screen=mock.Mock(return_value=image)),
        clipboard=SimpleNamespace(
            copy_image_file=mock.Mock(return_value=True),
            get_image=mock.Mock(return_value=image),
            read_text=mock.Mock(return_value=None),
            write_text=mock.Mock(return_value=True),
        ),
        opener=SimpleNamespace(
            open_path=mock.Mock(return_value=True),
            open_uri=mock.Mock(return_value=True),
        ),
        autostart=SimpleNamespace(is_supported=mock.Mock(return_value=True)),
        proxy_session=SimpleNamespace(
            setup=mock.Mock(),
            is_enabled=mock.Mock(return_value=False),
            enable=mock.Mock(),
            disable=mock.Mock(),
        ),
        hotkey_backend_factory=lambda app: SimpleNamespace(),
        tray_adapter=SimpleNamespace(),
    )

    monkeypatch.setattr("deskvane.features.capture.tool.get_platform_services", lambda: fake_services)

    app = SimpleNamespace(
        config=SimpleNamespace(
            screenshot=SimpleNamespace(
                notifications_enabled=True,
                save_to_disk=False,
                copy_to_clipboard=True,
                save_dir="~/Pictures/DeskVane",
            )
        ),
        root=SimpleNamespace(
            winfo_screenwidth=lambda: 100,
            winfo_screenheight=lambda: 80,
            after=lambda delay, callback: None,
        ),
        notifier=fake_services.notification,
    )
    tool = ScreenshotTool(app)
    pinned = []
    monkeypatch.setattr(tool, "_create_pinned_image", lambda img, x, y: pinned.append((img, x, y)))

    tool.pin_clipboard()

    assert pinned == [(image, 45, 36)]
    fake_services.clipboard.get_image.assert_called_once()
