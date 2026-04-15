from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class ProxyStatus:
    http_proxy: str | None = None
    https_proxy: str | None = None

    @property
    def enabled(self) -> bool:
        return self.http_proxy is not None or self.https_proxy is not None

    @property
    def display(self) -> str:
        if not self.enabled:
            return "未设置"
        parts: list[str] = []
        if self.http_proxy:
            parts.append(f"http: {self.http_proxy}")
        if self.https_proxy:
            parts.append(f"https: {self.https_proxy}")
        return " | ".join(parts)


class GitProxyManager:
    """Manage global git proxy settings via ``git config --global``."""

    @staticmethod
    def get_status() -> ProxyStatus:
        return ProxyStatus(
            http_proxy=GitProxyManager._git_get("http.proxy"),
            https_proxy=GitProxyManager._git_get("https.proxy"),
        )

    @staticmethod
    def enable(address: str) -> None:
        """Set both http.proxy and https.proxy to *address*."""
        subprocess.run(
            ["git", "config", "--global", "http.proxy", address],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "--global", "https.proxy", address],
            check=True,
            capture_output=True,
        )

    @staticmethod
    def disable() -> None:
        """Remove both http.proxy and https.proxy."""
        for key in ("http.proxy", "https.proxy"):
            subprocess.run(
                ["git", "config", "--global", "--unset", key],
                capture_output=True,
            )

    @staticmethod
    def _git_get(key: str) -> str | None:
        result = subprocess.run(
            ["git", "config", "--global", "--get", key],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None
