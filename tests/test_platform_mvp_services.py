from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from PIL import Image

from deskvane.platform.macos.capture import MacOSClipboardService, MacOSScreenCaptureService
from deskvane.platform.macos.notification import MacOSNotificationService
from deskvane.platform.macos.autostart import MacOSAutostartService
from deskvane.platform.windows.autostart import WindowsAutostartService
from deskvane.platform.windows.capture import WindowsClipboardService, WindowsScreenCaptureService
from deskvane.platform.windows.notification import WindowsNotificationService


def test_windows_notification_uses_powershell() -> None:
    service = WindowsNotificationService()

    with mock.patch("deskvane.platform.windows.notification.subprocess.Popen") as popen:
        service.show("DeskVane", "hello")

    args = popen.call_args.args[0]
    env = popen.call_args.kwargs["env"]
    assert args[:3] == ["powershell", "-NoProfile", "-Command"]
    assert env["DV_TITLE"] == "DeskVane"
    assert env["DV_BODY"] == "hello"
    assert "PATH" in env


def test_macos_notification_uses_osascript() -> None:
    service = MacOSNotificationService()

    with mock.patch("deskvane.platform.macos.notification.subprocess.Popen") as popen:
        service.show("DeskVane", "hello")

    popen.assert_called_once()
    assert popen.call_args.args[0][0:2] == ["osascript", "-e"]


def test_windows_clipboard_text_roundtrip_uses_powershell() -> None:
    service = WindowsClipboardService()
    run_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        run_calls.append((args, kwargs))
        if "Get-Clipboard -Raw" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="hello")
        return SimpleNamespace(returncode=0)

    with mock.patch("deskvane.platform.windows.capture.subprocess.run", side_effect=fake_run):
        assert service.write_text("world") is True
        assert service.read_text() == "hello"

    assert run_calls[0][0][:2] == ["powershell", "-NoProfile"]
    assert run_calls[0][1]["input"] == "world"
    assert run_calls[1][0][:2] == ["powershell", "-NoProfile"]


def test_macos_clipboard_text_roundtrip_uses_pbcopy_pbpaste() -> None:
    service = MacOSClipboardService()
    run_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        run_calls.append((args, kwargs))
        if args[0] == "pbpaste":
            return SimpleNamespace(returncode=0, stdout="hello")
        return SimpleNamespace(returncode=0)

    with mock.patch("deskvane.platform.macos.capture.subprocess.run", side_effect=fake_run):
        assert service.write_text("world") is True
        assert service.read_text() == "hello"

    assert run_calls[0][0] == ["pbcopy"]
    assert run_calls[0][1]["input"] == "world"
    assert run_calls[1][0] == ["pbpaste"]


def test_windows_screen_capture_prefers_image_grab() -> None:
    image = Image.new("RGB", (4, 4), "white")
    service = WindowsScreenCaptureService()

    with mock.patch("PIL.ImageGrab.grab", return_value=image) as grab:
        assert service.grab_full_screen() is image

    grab.assert_called_once_with(all_screens=True)


def test_macos_screen_capture_uses_image_grab() -> None:
    image = Image.new("RGB", (4, 4), "white")
    service = MacOSScreenCaptureService()

    with mock.patch("PIL.ImageGrab.grab", return_value=image) as grab:
        assert service.grab_full_screen() is image

    grab.assert_called_once_with()


def test_windows_autostart_writes_startup_script(tmp_path) -> None:
    service = WindowsAutostartService(startup_dir=tmp_path, entry_name="DeskVane.cmd", command="deskvane")

    assert service.is_enabled() is False
    assert service.enable("deskvane --minimized") is True
    assert service.is_enabled() is True
    assert (tmp_path / "DeskVane.cmd").read_text(encoding="utf-8").splitlines() == [
        "@echo off",
        "deskvane --minimized",
    ]
    assert service.disable() is True
    assert service.is_enabled() is False


def test_macos_autostart_writes_launch_agent(tmp_path) -> None:
    service = MacOSAutostartService(launch_agents_dir=tmp_path, label="io.github.deskvane", command="deskvane")

    assert service.is_enabled() is False
    assert service.enable("deskvane --minimized") is True
    contents = (tmp_path / "io.github.deskvane.plist").read_text(encoding="utf-8")
    assert "io.github.deskvane" in contents
    assert "deskvane --minimized" in contents
    assert service.disable() is True
    assert service.is_enabled() is False
