from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role
from app.schemas.clients import CategoryTimeSpentResponse, ClientSummary, TimeSpentResponse
from app.schemas.common import EffectiveRange, Page, SortOrder, resolve_range
from app.schemas.events import EventDetail
from app.services.client_service import get_client_activity, get_client_summary, list_clients
from app.services.time_spent_service import get_time_spent, get_time_spent_by_category

router = APIRouter(prefix="/api", tags=["clients"])


@router.get("/clients", response_model=Page[ClientSummary], dependencies=[Depends(require_any_role)])
async def read_clients(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="total_requests"),
    order: SortOrder = Query(default=SortOrder.DESC),
    search: str | None = Query(default=None, max_length=255),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Page[ClientSummary]:
    return await list_clients(
        db, effective_range.since, effective_range.until, limit, offset, sort_by, order, search, branch
    )


@router.get(
    "/clients/{client_ip}/summary",
    response_model=ClientSummary,
    dependencies=[Depends(require_any_role)],
)
async def read_client_summary(
    client_ip: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    return await get_client_summary(db, client_ip, effective_range.since, effective_range.until, branch)


@router.get(
    "/clients/{client_ip}/activity",
    response_model=Page[EventDetail],
    dependencies=[Depends(require_any_role)],
)
async def read_client_activity(
    client_ip: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    blocked_only: bool = Query(default=False),
    domain: str | None = Query(default=None, max_length=255),
    method: str | None = Query(default=None, max_length=16),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Page[EventDetail]:
    return await get_client_activity(
        db,
        client_ip,
        effective_range.since,
        effective_range.until,
        limit,
        offset,
        blocked_only,
        domain,
        method,
        branch,
    )


@router.get(
    "/clients/{client_ip}/time-spent",
    response_model=TimeSpentResponse,
    dependencies=[Depends(require_any_role)],
)
async def read_client_time_spent(
    client_ip: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> TimeSpentResponse:
    items = await get_time_spent(db, client_ip, effective_range.since, effective_range.until, branch)
    return TimeSpentResponse(items=items)


@router.get(
    "/clients/{client_ip}/time-spent-by-category",
    response_model=CategoryTimeSpentResponse,
    dependencies=[Depends(require_any_role)],
)
async def read_client_time_spent_by_category(
    client_ip: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> CategoryTimeSpentResponse:
    items = await get_time_spent_by_category(
        db, client_ip, effective_range.since, effective_range.until, branch
    )
    return CategoryTimeSpentResponse(items=items)
