from __future__ import annotations

import subprocess

from ..base import NotificationService


class MacOSNotificationService(NotificationService):
    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        script = (
            'display notification "{}" with title "{}"'.format(
                body.replace('"', '\\"'),
                title.replace('"', '\\"'),
            )
        )
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
