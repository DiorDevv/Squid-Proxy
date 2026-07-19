from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role
from app.models.domain_category import DomainCategoryLabel
from app.schemas.common import EffectiveRange, Page, SortOrder, resolve_range
from app.schemas.domains import CategoryStatsResponse, DomainClientStat, DomainStatsResponse, DomainSummary
from app.services.domain_service import get_domain_clients, get_domain_summary
from app.services.stats_service import get_top_domains, get_usage_by_category

router = APIRouter(prefix="/api", tags=["domains"])


@router.get("/top-domains", response_model=DomainStatsResponse, dependencies=[Depends(require_any_role)])
async def read_top_domains(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=10, ge=1, le=100),
    category: DomainCategoryLabel | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DomainStatsResponse:
    items = await get_top_domains(
        db,
        effective_range.since,
        effective_range.until,
        limit,
        blocked_only=False,
        order_by="requests",
        category=category,
    )
    return DomainStatsResponse(items=items)


@router.get("/top-blocked", response_model=DomainStatsResponse, dependencies=[Depends(require_any_role)])
async def read_top_blocked(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=10, ge=1, le=100),
    category: DomainCategoryLabel | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DomainStatsResponse:
    items = await get_top_domains(
        db,
        effective_range.since,
        effective_range.until,
        limit,
        blocked_only=True,
        order_by="blocked",
        category=category,
    )
    return DomainStatsResponse(items=items)


@router.get("/top-data-usage", response_model=DomainStatsResponse, dependencies=[Depends(require_any_role)])
async def read_top_data_usage(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=10, ge=1, le=100),
    category: DomainCategoryLabel | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DomainStatsResponse:
    items = await get_top_domains(
        db,
        effective_range.since,
        effective_range.until,
        limit,
        blocked_only=False,
        order_by="bytes",
        category=category,
    )
    return DomainStatsResponse(items=items)


@router.get(
    "/domains/by-category",
    response_model=CategoryStatsResponse,
    dependencies=[Depends(require_any_role)],
)
async def read_usage_by_category(
    effective_range: EffectiveRange = Depends(resolve_range),
    db: AsyncSession = Depends(get_db),
) -> CategoryStatsResponse:
    items = await get_usage_by_category(db, effective_range.since, effective_range.until)
    return CategoryStatsResponse(items=items)


@router.get(
    "/domains/{domain}/summary",
    response_model=DomainSummary,
    dependencies=[Depends(require_any_role)],
)
async def read_domain_summary(
    domain: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    db: AsyncSession = Depends(get_db),
) -> DomainSummary:
    return await get_domain_summary(db, domain, effective_range.since, effective_range.until)


@router.get(
    "/domains/{domain}/clients",
    response_model=Page[DomainClientStat],
    dependencies=[Depends(require_any_role)],
)
async def read_domain_clients(
    domain: str,
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="visit_count"),
    order: SortOrder = Query(default=SortOrder.DESC),
    db: AsyncSession = Depends(get_db),
) -> Page[DomainClientStat]:
    return await get_domain_clients(
        db, domain, effective_range.since, effective_range.until, limit, offset, sort_by, order
    )
