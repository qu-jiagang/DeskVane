from __future__ import annotations

import os
import shutil
import subprocess
import tkinter as tk
from dataclasses import dataclass

PRIMARY = "primary"
CLIPBOARD = "clipboard"


@dataclass(slots=True)
class ClipboardBackend:
    name: str
    supports_primary: bool
    supports_clipboard: bool

    def read_text(self, source: str) -> str | None:
        raise NotImplementedError

    def write_clipboard(self, text: str) -> bool:
        return False


class CommandClipboardBackend(ClipboardBackend):
    timeout_s = 0.4

    def run_command(self, args: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout


class WlClipboardBackend(CommandClipboardBackend):
    def __init__(self) -> None:
        super().__init__("wl-clipboard", True, True)

    def read_text(self, source: str) -> str | None:
        args = ["wl-paste", "--no-newline"]
        if source == PRIMARY:
            args.insert(1, "--primary")
        return self.run_command(args)

    def write_clipboard(self, text: str) -> bool:
        if shutil.which("wl-copy") is None:
            return False
        try:
            subprocess.run(
                ["wl-copy"],
                input=text,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return True


class XclipClipboardBackend(CommandClipboardBackend):
    def __init__(self) -> None:
        super().__init__("xclip", True, True)

    def read_text(self, source: str) -> str | None:
        selection = "primary" if source == PRIMARY else "clipboard"
        return self.run_command(["xclip", "-selection", selection, "-o"])

    def write_clipboard(self, text: str) -> bool:
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return True


class XselClipboardBackend(CommandClipboardBackend):
    def __init__(self) -> None:
        super().__init__("xsel", True, True)

    def read_text(self, source: str) -> str | None:
        selection = "--primary" if source == PRIMARY else "--clipboard"
        return self.run_command(["xsel", selection, "--output"])

    def write_clipboard(self, text: str) -> bool:
        try:
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return True


class TkClipboardBackend(ClipboardBackend):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__("tk", True, True)
        self.root = root

    def read_text(self, source: str) -> str | None:
        try:
            if source == PRIMARY:
                return self.root.selection_get(selection="PRIMARY")
            return self.root.clipboard_get()
        except tk.TclError:
            return None

    def write_clipboard(self, text: str) -> bool:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            return False
        return True


def choose_clipboard_backend(root: tk.Tk) -> ClipboardBackend:
    on_wayland = bool(os.getenv("WAYLAND_DISPLAY"))
    if on_wayland and shutil.which("wl-paste"):
        return WlClipboardBackend()
    if shutil.which("xclip"):
        return XclipClipboardBackend()
    if shutil.which("xsel"):
        return XselClipboardBackend()
    return TkClipboardBackend(root)

