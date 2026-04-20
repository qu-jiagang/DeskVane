from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class ManagedTask:
    name: str
    start: Callable[[], None]
    stop: Callable[[], None]
    started: bool = False


class TaskManager:
    """Minimal lifecycle registry for long-lived runtime tasks."""

    def __init__(self) -> None:
        self._tasks: list[ManagedTask] = []

    def register(self, name: str, start: Callable[[], None], stop: Callable[[], None]) -> None:
        self._tasks.append(ManagedTask(name=name, start=start, stop=stop))

    def start_all(self) -> None:
        for task in self._tasks:
            if task.started:
                continue
            task.start()
            task.started = True

    def stop_all(self) -> None:
        for task in reversed(self._tasks):
            if not task.started:
                continue
            task.stop()
            task.started = False
