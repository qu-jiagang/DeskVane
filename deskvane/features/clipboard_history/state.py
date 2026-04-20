from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClipboardHistoryState:
    enabled: bool
    item_count: int
    overlay_visible: bool
