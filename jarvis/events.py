"""Thread-safe publish/subscribe bus used to feed logs, status and history to the GUI."""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from typing import Any


class EventBus:
    def __init__(self, history_size: int = 500):
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)

    def publish(self, kind: str, **data: Any) -> dict[str, Any]:
        event = {"type": kind, "time": time.time(), **data}
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:  # slow consumer: drop the event rather than block the assistant
                pass
        return event

    def subscribe(self, maxsize: int = 1000) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def recent(self, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            items = [e for e in self._history if kind is None or e["type"] == kind]
        return items[-limit:]


class BusLogHandler(logging.Handler):
    """Forwards log records to the event bus so the GUI log view can show them."""

    def __init__(self, bus: EventBus):
        super().__init__()
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bus.publish("log", level=record.levelname, logger=record.name, message=record.getMessage())
        except Exception:  # never let logging crash the app
            self.handleError(record)
