from datetime import datetime

from pydantic import BaseModel

from app.models.raw_event import RawEvent
from app.services.log_parser import ParsedEvent


class EventDetail(BaseModel):
    """Canonical shape of a single Squid event on the wire -- used by
    /api/events/recent (ring buffer), /api/events (RawEvent, paginated), and
    the /ws/live broadcast, so all three can never drift out of sync the way
    three independently hand-rolled field lists eventually would."""

    id: int
    timestamp: datetime
    client_ip: str
    user: str | None
    method: str
    url: str
    domain: str | None
    action: str
    status_code: int
    bytes: int
    blocked: bool
    duration_ms: int | None = None
    hierarchy: str | None = None
    peer: str | None = None
    content_type: str | None = None

    @classmethod
    def from_parsed(cls, event_id: int, event: ParsedEvent) -> "EventDetail":
        return cls(
            id=event_id,
            timestamp=event.timestamp,
            client_ip=event.client_ip,
            user=event.user,
            method=event.method,
            url=event.url,
            domain=event.domain,
            action=event.action,
            status_code=event.status_code,
            bytes=event.bytes,
            blocked=event.blocked,
            duration_ms=event.duration_ms,
            hierarchy=event.hierarchy,
            peer=event.peer,
            content_type=event.content_type,
        )

    @classmethod
    def from_raw_event(cls, row: RawEvent) -> "EventDetail":
        return cls(
            id=row.id,
            timestamp=row.timestamp,
            client_ip=row.client_ip,
            user=row.user,
            method=row.method,
            url=row.url,
            domain=row.domain,
            action=row.action,
            status_code=row.status_code,
            bytes=row.bytes,
            blocked=row.blocked,
            duration_ms=row.duration_ms,
            hierarchy=row.hierarchy,
            peer=row.peer,
            content_type=row.content_type,
        )
