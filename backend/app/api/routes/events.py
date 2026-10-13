from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    get_db,
    require_admin_or_auditor,
    require_any_role,
    resolve_branch,
)
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.audit_log import AuditAction
from app.schemas.blocked_domains import BlockedDomainSort, BlockedDomainsResponse, BlockKind
from app.schemas.common import EffectiveRange, Page, resolve_range
from app.schemas.events import EventDetail
from app.services import audit_service, blocked_domain_export, blocked_domain_service
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
    # Only applies with blocked_only: "denied" drops the 407 login
    # challenges, "auth" keeps only them.
    block_kind: BlockKind = Query(default="all"),
    client_ip: str | None = Query(default=None),
    domain: str | None = Query(default=None, max_length=255),
    method: str | None = Query(default=None, max_length=16),
    user: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=255),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Page[EventDetail]:
    page = await get_events(
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
        block_kind=block_kind,
    )
    # Audit only a *targeted* query (someone looking for a specific person /
    # host / term), not a bare range browse -- which is also what the
    # WebSocket-down polling fallback re-issues every ~10s.
    targeted = {"search": search, "client_ip": client_ip, "domain": domain, "user": user}
    if any(targeted.values()):
        detail = ", ".join(f"{k}={v}" for k, v in targeted.items() if v)
        await audit_service.record_read_access(
            db,
            action=AuditAction.EVENT_SEARCH_RUN,
            actor_user_id=current_user.user_id,
            branch=branch,
            detail=detail,
        )
    return page


@router.get(
    "/blocked-domains", response_model=BlockedDomainsResponse, dependencies=[Depends(require_any_role)]
)
async def read_blocked_domains(
    effective_range: EffectiveRange = Depends(resolve_range),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    kind: BlockKind = Query(default="denied"),
    sort: BlockedDomainSort = Query(default="requests"),
    proxy: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=255),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BlockedDomainsResponse:
    """Blocked requests grouped by domain (hourly aggregates, not raw_events)."""
    return await blocked_domain_service.get_blocked_domains(
        db, effective_range.since, effective_range.until, branch=branch, proxy=proxy or None,
        search=search, kind=kind, sort=sort, limit=limit, offset=offset,
    )


@router.get("/blocked-domains/export", dependencies=[Depends(require_admin_or_auditor)])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def export_blocked_domains(
    request: Request,
    format: Literal["xlsx", "csv"] = Query(default="xlsx"),
    # "domain": a header-less CSV of just the domain names.
    columns: Literal["all", "domain"] = Query(default="all"),
    lang: Literal["uz", "en", "ru"] = Query(default="uz"),
    kind: BlockKind = Query(default="denied"),
    sort: BlockedDomainSort = Query(default="requests"),
    proxy: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=255),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """The whole blocked-domain list (every page) as an Excel or CSV file."""
    proxy = proxy or None
    rows = await blocked_domain_service.list_all_blocked_domains(
        db, effective_range.since, effective_range.until, branch=branch, proxy=proxy,
        search=search, kind=kind, sort=sort,
    )
    if format == "xlsx":
        columns = "all"
        content = blocked_domain_export.domains_xlsx(
            rows, lang, branch=branch, proxy=proxy, since=effective_range.since,
            until=effective_range.until, kind=kind, search=search, sort=sort,
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif columns == "domain":
        content = blocked_domain_export.domain_names_csv(rows)
        media_type = "text/csv; charset=utf-8"
    else:
        content = blocked_domain_export.domains_csv(rows, lang)
        media_type = "text/csv; charset=utf-8"
    await audit_service.record(
        db,
        action=AuditAction.EXPORT_CREATED,
        actor_user_id=current_user.user_id,
        branch=branch,
        detail=f"blocked-domains format={format} columns={columns} kind={kind} rows={len(rows)}"
        + (f" proxy={proxy}" if proxy else "")
        + (f" search={search}" if search else ""),
    )
    await db.commit()
    stamp = effective_range.until.strftime("%Y%m%d-%H%M")
    filename = f"bloklangan-domenlar-{branch or 'barcha'}-{stamp}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
