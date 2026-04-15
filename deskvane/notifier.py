from __future__ import annotations

import subprocess


class Notifier:
    """Thin wrapper around ``notify-send``."""

    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        try:
            subprocess.Popen(
                ["notify-send", "-t", str(timeout_ms), title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
