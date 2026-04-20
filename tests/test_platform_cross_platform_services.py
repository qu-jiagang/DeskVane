from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from PIL import Image

from deskvane.platform.macos.capture import MacOSClipboardService, MacOSScreenCaptureService
from deskvane.platform.windows.capture import WindowsClipboardService, WindowsScreenCaptureService


def test_windows_screen_capture_uses_imagegrab(monkeypatch) -> None:
    image = Image.new("RGB", (4, 3), "white")
    monkeypatch.setattr("PIL.ImageGrab.grab", lambda: image)

    service = WindowsScreenCaptureService()

    assert service.grab_full_screen() is image


def test_windows_clipboard_text_uses_powershell(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if "Get-Clipboard -Raw" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="hello")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("deskvane.platform.windows.capture.subprocess.run", fake_run)

    service = WindowsClipboardService()

    assert service.write_text("world") is True
    assert service.read_text() == "hello"
    assert calls[0][0][:3] == ["powershell", "-NoProfile", "-Command"]


def test_macos_screen_capture_uses_imagegrab(monkeypatch) -> None:
    image = Image.new("RGB", (4, 3), "white")
    monkeypatch.setattr("PIL.ImageGrab.grab", lambda: image)

    service = MacOSScreenCaptureService()

    assert service.grab_full_screen() is image


def test_macos_clipboard_text_uses_pbcopy_and_pbpaste(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "pbpaste":
            return SimpleNamespace(returncode=0, stdout="bonjour")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("deskvane.platform.macos.capture.subprocess.run", fake_run)

    service = MacOSClipboardService()

    assert service.write_text("salut") is True
    assert service.read_text() == "bonjour"
    assert calls[0][0] == ["pbcopy"]
