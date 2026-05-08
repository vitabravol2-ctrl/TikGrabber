from __future__ import annotations


class EventGuard:
    """Suppress duplicate events and emit only on transition."""

    def __init__(self) -> None:
        self._last_events: dict[str, str] = {}

    def should_emit(self, stream: str, event: str) -> bool:
        if not event:
            return False
        last = self._last_events.get(stream)
        if last == event:
            return False
        self._last_events[stream] = event
        return True

    def last_event(self, stream: str) -> str | None:
        return self._last_events.get(stream)
