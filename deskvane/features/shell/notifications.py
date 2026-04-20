from __future__ import annotations

from ...platform.base import NotificationService
from ...platform.factory import get_platform_services


class Notifier:
    """Compatibility wrapper around the active platform notification service."""

    def __init__(self, service: NotificationService | None = None) -> None:
        self._service = service or get_platform_services().notification

    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        self._service.show(title, body, timeout_ms)
