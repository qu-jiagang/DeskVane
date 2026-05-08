from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


TaskState = Literal["stopped", "running", "paused"]

@dataclass(slots=True)
class ManagedTask:
    name: str
    start: Callable[[], None]
    stop: Callable[[], None]
    pause: Callable[[], None]
    resume: Callable[[], None]
    state: TaskState = "stopped"


class TaskManager:
    """Minimal lifecycle registry for long-lived runtime tasks."""

    def __init__(self) -> None:
        self._tasks: list[ManagedTask] = []

    def register(
        self,
        name: str,
        start: Callable[[], None],
        stop: Callable[[], None],
        pause: Callable[[], None] | None = None,
        resume: Callable[[], None] | None = None,
    ) -> None:
        self._tasks.append(
            ManagedTask(
                name=name,
                start=start,
                stop=stop,
                pause=pause or stop,
                resume=resume or start,
            )
        )

    def _find(self, name: str) -> ManagedTask:
        for task in self._tasks:
            if task.name == name:
                return task
        raise KeyError(f"unknown task: {name}")

    def start(self, name: str) -> None:
        task = self._find(name)
        if task.state == "running":
            return
        if task.state == "paused":
            task.resume()
        else:
            task.start()
        task.state = "running"

    def stop(self, name: str) -> None:
        task = self._find(name)
        if task.state == "stopped":
            return
        task.stop()
        task.state = "stopped"

    def pause(self, name: str) -> None:
        task = self._find(name)
        if task.state != "running":
            return
        task.pause()
        task.state = "paused"

    def resume(self, name: str) -> None:
        task = self._find(name)
        if task.state == "running":
            return
        if task.state == "stopped":
            task.start()
        else:
            task.resume()
        task.state = "running"

    def state(self, name: str) -> TaskState:
        return self._find(name).state

    def start_all(self) -> None:
        for task in self._tasks:
            if task.state == "running":
                continue
            if task.state == "paused":
                task.resume()
            else:
                task.start()
            task.state = "running"

    def stop_all(self) -> None:
        for task in reversed(self._tasks):
            if task.state == "stopped":
                continue
            task.stop()
            task.state = "stopped"

    def pause_all(self) -> None:
        for task in reversed(self._tasks):
            if task.state != "running":
                continue
            task.pause()
            task.state = "paused"

    def resume_all(self) -> None:
        for task in self._tasks:
            if task.state == "running":
                continue
            if task.state == "paused":
                task.resume()
            else:
                task.start()
            task.state = "running"
