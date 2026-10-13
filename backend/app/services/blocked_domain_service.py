"""Blocked domains, one row per domain -- the Blocked page's "Domains" view
and its export. Reads only the hourly aggregates (see
app/models/blocked_domain_aggregate.py), never raw_events.

Ranges are matched at hour granularity: an hour bucket is included when it
starts inside [floor_hour(since), until].
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_domain_aggregate import (
    BlockedDomainClientHourlyAggregate as ClientAgg,
)
from app.models.blocked_domain_aggregate import (
    BlockedDomainHourlyAggregate as DomainAgg,
)
from app.schemas.blocked_domains import (
    BlockedDomainRow,
    BlockedDomainSort,
    BlockedDomainsResponse,
    BlockKind,
)

# Hard cap for an export -- a week has ~8k blocked domains.
EXPORT_MAX_ROWS = 50_000
# Above this many domains, per-page lookups skip the IN (...) list.
_IN_LIST_MAX = 500


def _floor_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _conditions(
    table: type[DomainAgg] | type[ClientAgg],
    since: datetime,
    until: datetime,
    branch: str | None,
    proxy: str | None,
    search: str | None,
) -> list[ColumnElement[bool]]:
    conditions = [table.bucket_ts >= _floor_hour(since), table.bucket_ts <= until]
    if branch:
        conditions.append(table.branch == branch)
    if proxy:
        conditions.append(table.proxy == proxy)
    if search and search.strip():
        conditions.append(table.domain.ilike(f"%{search.strip()}%"))
    return conditions


def _row_has_kind(table: type[DomainAgg] | type[ClientAgg], kind: BlockKind) -> ColumnElement[bool]:
    if kind == "denied":
        return table.denied_count > 0
    if kind == "auth":
        return table.auth_count > 0
    return (table.denied_count + table.auth_count) > 0


async def _list(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    *,
    branch: str | None,
    proxy: str | None,
    search: str | None,
    kind: BlockKind,
    sort: BlockedDomainSort,
    limit: int,
    offset: int,
) -> tuple[list[BlockedDomainRow], int]:
    conditions = _conditions(DomainAgg, since, until, branch, proxy, search)
    denied = func.sum(DomainAgg.denied_count).label("denied")
    auth = func.sum(DomainAgg.auth_count).label("auth")
    first_seen = func.min(DomainAgg.bucket_ts).label("first_seen")
    last_seen = func.max(DomainAgg.bucket_ts).label("last_seen")
    measure = {
        "denied": func.sum(DomainAgg.denied_count),
        "auth": func.sum(DomainAgg.auth_count),
        "all": func.sum(DomainAgg.denied_count + DomainAgg.auth_count),
    }[kind]

    grouped = (
        select(DomainAgg.domain, denied, auth, first_seen, last_seen)
        .where(*conditions)
        .group_by(DomainAgg.domain)
        .having(measure > 0)
    )
    total = (await session.execute(select(func.count()).select_from(grouped.subquery()))).scalar_one()

    # Ties always break by domain so a row never repeats or goes missing
    # across page boundaries.
    if sort == "domain":
        order = [DomainAgg.domain.asc()]
    elif sort == "last":
        order = [last_seen.desc(), measure.desc(), DomainAgg.domain.asc()]
    else:
        order = [measure.desc(), DomainAgg.domain.asc()]
    page = (await session.execute(grouped.order_by(*order).limit(limit).offset(offset))).all()
    if not page:
        return [], total

    domains = [row.domain for row in page]
    # A UI page is narrowed with IN; an export's thousands of domains would
    # overrun the driver's bind-parameter limit, so it reads the whole
    # filtered range instead and the dict lookups below pick its rows.
    in_page = len(domains) <= _IN_LIST_MAX
    where_page = [*conditions, _row_has_kind(DomainAgg, kind)]
    if in_page:
        where_page.append(DomainAgg.domain.in_(domains))
    branches: dict[str, set[str]] = defaultdict(set)
    proxies: dict[str, set[str]] = defaultdict(set)
    for domain, row_branch, row_proxy in (
        await session.execute(
            select(DomainAgg.domain, DomainAgg.branch, DomainAgg.proxy).where(*where_page).distinct()
        )
    ).all():
        branches[domain].add(row_branch)
        if row_proxy:
            proxies[domain].add(row_proxy)

    client_conditions = [
        *_conditions(ClientAgg, since, until, branch, proxy, None if in_page else search),
        _row_has_kind(ClientAgg, kind),
    ]
    if in_page:
        client_conditions.append(ClientAgg.domain.in_(domains))
    clients = dict(
        (
            await session.execute(
                select(ClientAgg.domain, func.count(func.distinct(ClientAgg.client_ip)))
                .where(*client_conditions)
                .group_by(ClientAgg.domain)
            )
        ).all()
    )

    rows = [
        BlockedDomainRow(
            domain=row.domain,
            denied_count=row.denied or 0,
            auth_count=row.auth or 0,
            client_count=clients.get(row.domain, 0),
            branches=sorted(branches[row.domain]),
            proxies=sorted(proxies[row.domain]),
            first_seen=row.first_seen,
            last_seen=row.last_seen,
        )
        for row in page
    ]
    return rows, total


async def get_blocked_domains(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    *,
    branch: str | None = None,
    proxy: str | None = None,
    search: str | None = None,
    kind: BlockKind = "denied",
    sort: BlockedDomainSort = "requests",
    limit: int = 50,
    offset: int = 0,
) -> BlockedDomainsResponse:
    rows, total = await _list(
        session, since, until, branch=branch, proxy=proxy, search=search, kind=kind, sort=sort,
        limit=limit, offset=offset,
    )
    conditions = _conditions(DomainAgg, since, until, branch, proxy, search)
    denied_total, auth_total = (
        await session.execute(
            select(
                func.coalesce(func.sum(DomainAgg.denied_count), 0),
                func.coalesce(func.sum(DomainAgg.auth_count), 0),
            ).where(*conditions)
        )
    ).one()
    # Deliberately not narrowed by `proxy`/`search`: the filter has to keep
    # offering the other proxies once one is picked.
    available = (
        await session.execute(
            select(DomainAgg.proxy)
            .where(*_conditions(DomainAgg, since, until, branch, None, None), DomainAgg.proxy != "")
            .distinct()
            .order_by(DomainAgg.proxy)
        )
    ).scalars().all()
    return BlockedDomainsResponse(
        items=rows,
        total=total,
        limit=limit,
        offset=offset,
        denied_total=denied_total,
        auth_total=auth_total,
        available_proxies=list(available),
    )


async def list_all_blocked_domains(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    *,
    branch: str | None = None,
    proxy: str | None = None,
    search: str | None = None,
    kind: BlockKind = "denied",
    sort: BlockedDomainSort = "requests",
) -> list[BlockedDomainRow]:
    """Every matching domain (up to EXPORT_MAX_ROWS), for the export."""
    rows, _ = await _list(
        session, since, until, branch=branch, proxy=proxy, search=search, kind=kind, sort=sort,
        limit=EXPORT_MAX_ROWS, offset=0,
    )
    return rows
