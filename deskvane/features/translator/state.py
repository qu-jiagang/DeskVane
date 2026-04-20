from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranslatorState:
    enabled: bool
    paused: bool
    running: bool
    status_key: str
    status_text: str
    model_label: str
    backend_label: str
    last_translation_available: bool
    last_translation_preview: str
