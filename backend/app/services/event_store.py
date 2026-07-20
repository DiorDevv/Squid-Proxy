"""In-memory ring buffer of the most recent parsed log events.

Serves /ws/live, /api/events/recent, and the live ticker only — every
bucketed/aggregate endpoint reads from the database instead, so there is a
single source of truth for counts (see ARCHITECTURE.md).
"""

import itertools
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from app.services.log_parser import ParsedEvent


@dataclass(slots=True, frozen=True)
class StoredEvent:
    id: int
    event: ParsedEvent


class RingBuffer:
    def __init__(self, max_events: int) -> None:
        self._buffer: deque[StoredEvent] = deque(maxlen=max_events)
        self._counter = itertools.count(1)
        self._latest_id = 0

    def append(self, event: ParsedEvent) -> StoredEvent:
        stored = StoredEvent(id=next(self._counter), event=event)
        self._buffer.append(stored)
        self._latest_id = stored.id
        return stored

    @property
    def latest_id(self) -> int:
        """The most recently assigned event id, 0 if nothing's arrived yet.
        Lets a consumer (see Aggregator.backlog_size) compute how far behind
        it's fallen without materializing events_since()'s whole list just
        to count it."""
        return self._latest_id

    @property
    def max_events(self) -> int:
        return self._buffer.maxlen or 0

    def recent(
        self,
        limit: int = 100,
        blocked_only: bool = False,
        client_ip: str | None = None,
        branch: str | None = None,
    ) -> list[StoredEvent]:
        results: list[StoredEvent] = []
        for stored in reversed(self._buffer):
            if blocked_only and not stored.event.blocked:
                continue
            if client_ip and stored.event.client_ip != client_ip:
                continue
            if branch and stored.event.branch != branch:
                continue
            results.append(stored)
            if len(results) >= limit:
                break
        return results

    def events_since(self, last_id: int) -> list[StoredEvent]:
        """Events with id > last_id, oldest first. Used by the aggregator's periodic flush."""
        newer: list[StoredEvent] = []
        for stored in reversed(self._buffer):
            if stored.id <= last_id:
                break
            newer.append(stored)
        newer.reverse()
        return newer

    def drain_snapshot(self) -> Iterator[StoredEvent]:
        """Iterate a point-in-time snapshot, oldest first."""
        return iter(list(self._buffer))

    def __len__(self) -> int:
        return len(self._buffer)
