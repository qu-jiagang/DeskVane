from __future__ import annotations

import os
import subprocess

from ..base import NotificationService


class WindowsNotificationService(NotificationService):
    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        script = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$env:DV_TITLE</text><text>$env:DV_BODY</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DeskVane')
$notifier.Show($toast)
        """
        try:
            env = os.environ.copy()
            env.update({"DV_TITLE": title, "DV_BODY": body})
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", script],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
