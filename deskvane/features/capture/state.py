from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaptureState:
    save_dir: str
    copy_to_clipboard: bool
    save_to_disk: bool
    notifications_enabled: bool
