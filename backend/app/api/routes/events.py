from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import require_any_role
from app.schemas.events import EventOut

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events/recent", response_model=list[EventOut], dependencies=[Depends(require_any_role)])
async def read_recent_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    blocked_only: bool = Query(default=False),
    client_ip: str | None = Query(default=None),
) -> list[EventOut]:
    ring_buffer = request.app.state.ring_buffer
    stored_events = ring_buffer.recent(limit=limit, blocked_only=blocked_only, client_ip=client_ip)
    return [
        EventOut(
            id=stored.id,
            timestamp=stored.event.timestamp,
            client_ip=stored.event.client_ip,
            action=stored.event.action,
            status_code=stored.event.status_code,
            method=stored.event.method,
            url=stored.event.url,
            domain=stored.event.domain,
            user=stored.event.user,
            bytes=stored.event.bytes,
            blocked=stored.event.blocked,
        )
        for stored in stored_events
    ]
