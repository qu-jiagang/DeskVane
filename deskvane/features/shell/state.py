from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShellState:
    tray_supports_menu: bool
    notifications_enabled: bool
    clipboard_history_enabled: bool
    git_proxy_enabled: bool
    terminal_proxy_enabled: bool
    terminal_proxy_supported: bool
