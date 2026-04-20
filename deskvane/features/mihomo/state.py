from __future__ import annotations

from dataclasses import dataclass

from ...mihomo.api import MihomoRuntimeState
from ...mihomo.core_manager import MihomoCoreStatus


@dataclass(frozen=True, slots=True)
class MihomoFeatureState:
    installed: bool
    running: bool
    backend: str
    title: str
    party_supported: bool
    has_external_ui: bool
    pac_enabled: bool
    subscription_url: str
    saved_subscriptions: tuple[str, ...]
    runtime: MihomoRuntimeState
    core_status: MihomoCoreStatus
