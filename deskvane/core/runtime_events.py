from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    id: int
    timestamp: str
    level: str
    topic: str
    message: str
    data: dict[str, Any]


class RuntimeEventStore:
    """In-memory ring buffer for UI-facing runtime events."""

    def __init__(self, capacity: int = 200) -> None:
        self._events: deque[RuntimeEvent] = deque(maxlen=capacity)
        self._ids = count(1)
        self._lock = Lock()

    def add(
        self,
        topic: str,
        message: str,
        *,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            id=next(self._ids),
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            topic=topic,
            message=message,
            data=data or {},
        )
        with self._lock:
            self._events.append(event)
        return event

    def list(self, after_id: int | None = None, limit: int | None = None) -> list[RuntimeEvent]:
        with self._lock:
            events = list(self._events)
        if after_id is not None:
            events = [event for event in events if event.id > after_id]
        if limit is not None and limit >= 0:
            events = events[-limit:]
        return events
