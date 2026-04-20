from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxyState:
    address: str
    git_proxy_enabled: bool
    terminal_proxy_enabled: bool
    terminal_proxy_supported: bool
    git_proxy_status_display: str
    terminal_proxy_status_display: str
