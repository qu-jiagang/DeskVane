from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ..config import AppConfig, _save_config, load_config


class ConfigManager:
    """Thin configuration facade used by the application kernel."""

    def __init__(self) -> None:
        self._current: AppConfig | None = None
        self._subscribers: list[Callable[[AppConfig], None]] = []

    def load(self) -> AppConfig:
        self._current = load_config()
        return self._current

    def save(self, config: AppConfig) -> None:
        self._current = config
        _save_config(config)
        for callback in list(self._subscribers):
            callback(config)

    def snapshot(self, config: AppConfig) -> AppConfig:
        return replace(config)

    @property
    def current(self) -> AppConfig | None:
        return self._current

    def subscribe(self, callback: Callable[[AppConfig], None]) -> None:
        self._subscribers.append(callback)
