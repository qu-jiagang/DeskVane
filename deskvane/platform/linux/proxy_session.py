from __future__ import annotations

from ...features.proxy.terminal_proxy import TerminalProxyManager
from ..base import ProxySessionService


class LinuxProxySessionService(ProxySessionService):
    def setup(self) -> None:
        TerminalProxyManager.setup_hooks()

    def is_enabled(self) -> bool:
        return TerminalProxyManager.get_status().enabled

    def enable(self, address: str) -> None:
        TerminalProxyManager.enable(address)

    def disable(self, address: str | None = None) -> None:
        TerminalProxyManager.disable(address)
