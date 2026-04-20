from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubconverterState:
    enabled: bool
    port: int
    running: bool
