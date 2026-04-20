"""Platform service accessors for DeskVane."""

from __future__ import annotations

from .base import ClipboardService, NotificationService, PlatformInfo, PlatformServices, ScreenCaptureService
from .factory import create_platform_services, get_platform_services

__all__ = [
    "ClipboardService",
    "NotificationService",
    "PlatformInfo",
    "PlatformServices",
    "ScreenCaptureService",
    "create_platform_services",
    "get_platform_services",
]
