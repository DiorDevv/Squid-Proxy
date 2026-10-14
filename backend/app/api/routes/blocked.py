"""The Blocked page's Analysis view: summary, grouped list and its export,
all under the shared filter language (app/services/block_filters.py)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    get_db,
    require_any_role,
    require_permission,
    resolve_branch,
)
from app.core.branch_scope import BranchScope, scope_label
from app.core.config import get_settings
from app.core.permissions import EXPORT
from app.core.rate_limit import limiter
from app.models.audit_log import AuditAction
from app.schemas.blocked_domains import (
    BlockGroupBy,
    BlockGroupSort,
    BlockGroupsResponse,
    BlockKind,
    BlockSummary,
)
from app.schemas.common import EffectiveRange, resolve_range
from app.services import audit_service, blocked_analysis_service, blocked_group_export
from app.services.block_filters import BlockFilters, FilterError, parse_filters

router = APIRouter(prefix="/api/blocked", tags=["blocked"], dependencies=[Depends(require_any_role)])


def block_filters(
    domains: str | None = Query(default=None, max_length=2000),
    clients: str | None = Query(default=None, max_length=2000),
    users: str | None = Query(default=None, max_length=2000),
    proxy: str | None = Query(default=None, max_length=64),
) -> BlockFilters:
    try:
        return parse_filters(domains, clients, users, proxy)
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary", response_model=BlockSummary)
async def read_summary(
    kind: BlockKind = Query(default="denied"),
    filters: BlockFilters = Depends(block_filters),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: BranchScope = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BlockSummary:
    return await blocked_analysis_service.get_summary(
        db, effective_range.since, effective_range.until, branch, filters, kind=kind
    )


@router.get("/groups", response_model=BlockGroupsResponse)
async def read_groups(
    group: BlockGroupBy = Query(default="domain"),
    kind: BlockKind = Query(default="denied"),
    sort: BlockGroupSort = Query(default="requests"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    filters: BlockFilters = Depends(block_filters),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: BranchScope = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BlockGroupsResponse:
    result = await blocked_analysis_service.get_groups(
        db, effective_range.since, effective_range.until, branch, filters,
        group=group, kind=kind, sort=sort, limit=limit, offset=offset,
    )
    # Same rule as /api/events: a lookup of specific people/hosts is audited,
    # a plain browse is not.
    targeted = []
    if filters.clients:
        targeted.append("clients=" + ",".join([*filters.clients.exact, *filters.clients.prefixes]))
    if filters.users:
        targeted.append("users=" + ",".join(filters.users.terms) + (",-" if filters.users.no_login else ""))
    if targeted:
        await audit_service.record_read_access(
            db,
            action=AuditAction.EVENT_SEARCH_RUN,
            actor_user_id=current_user.user_id,
            branch=branch,
            detail=f"blocked-analysis group={group} " + " ".join(targeted),
        )
    return result


@router.get("/groups/export", dependencies=[Depends(require_permission(EXPORT))])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def export_groups(
    request: Request,
    format: Literal["xlsx", "csv"] = Query(default="xlsx"),
    # "key": a header-less CSV of just the grouped values (domains, IPs ...).
    columns: Literal["all", "key"] = Query(default="all"),
    lang: Literal["uz", "en", "ru"] = Query(default="uz"),
    group: BlockGroupBy = Query(default="domain"),
    kind: BlockKind = Query(default="denied"),
    sort: BlockGroupSort = Query(default="requests"),
    domains: str | None = Query(default=None, max_length=2000),
    clients: str | None = Query(default=None, max_length=2000),
    users: str | None = Query(default=None, max_length=2000),
    proxy: str | None = Query(default=None, max_length=64),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: BranchScope = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """The whole grouped list (every page) as an Excel or CSV file."""
    filters = block_filters(domains, clients, users, proxy)
    rows = await blocked_analysis_service.list_all_groups(
        db, effective_range.since, effective_range.until, branch, filters, group=group, kind=kind, sort=sort
    )
    applied = [
        (name, value)
        for name, value in (("domains", domains), ("clients", clients), ("users", users), ("proxy", proxy))
        if value and value.strip()
    ]
    if format == "xlsx":
        columns = "all"
        content = blocked_group_export.groups_xlsx(
            rows, group, lang, branch=branch, since=effective_range.since, until=effective_range.until,
            kind=kind, sort=sort, filters=applied,
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif columns == "key":
        content = blocked_group_export.group_keys_csv(rows)
        media_type = "text/csv; charset=utf-8"
    else:
        content = blocked_group_export.groups_csv(rows, group, lang)
        media_type = "text/csv; charset=utf-8"
    await audit_service.record(
        db,
        action=AuditAction.EXPORT_CREATED,
        actor_user_id=current_user.user_id,
        branch=branch,
        detail=f"blocked-{group} format={format} columns={columns} kind={kind} rows={len(rows)}"
        + "".join(f" {name}={value.strip()}" for name, value in applied),
    )
    await db.commit()
    stamp = effective_range.until.strftime("%Y%m%d-%H%M")
    filename = f"bloklangan-{group}-{scope_label(branch, '+') or 'barcha'}-{stamp}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
