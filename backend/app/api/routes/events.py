from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role, resolve_branch
from app.schemas.common import EffectiveRange, Page, resolve_range
from app.schemas.events import EventDetail
from app.services.event_query_service import get_events

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events/recent", response_model=list[EventDetail], dependencies=[Depends(require_any_role)])
async def read_recent_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    blocked_only: bool = Query(default=False),
    client_ip: str | None = Query(default=None),
    branch: str | None = Depends(resolve_branch),
) -> list[EventDetail]:
    ring_buffer = request.app.state.ring_buffer
    stored_events = ring_buffer.recent(
        limit=limit, blocked_only=blocked_only, client_ip=client_ip, branch=branch
    )
    return [EventDetail.from_parsed(stored.id, stored.event) for stored in stored_events]


@router.get("/events", response_model=Page[EventDetail], dependencies=[Depends(require_any_role)])
async def read_events(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    blocked_only: bool = Query(default=False),
    client_ip: str | None = Query(default=None),
    domain: str | None = Query(default=None, max_length=255),
    method: str | None = Query(default=None, max_length=16),
    user: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=255),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> Page[EventDetail]:
    return await get_events(
        db,
        effective_range.since,
        effective_range.until,
        limit,
        offset,
        blocked_only,
        client_ip,
        domain,
        method,
        user,
        search,
        branch,
    )
