"""The Blocked page's Analysis view: blocked requests under the shared
filters (block_filters.py), summarised and grouped by domain / client IP /
login / subnet / branch / proxy. Reads only the hourly aggregates (see
app/models/blocked_domain_aggregate.py), never raw_events.

Two tables, one rule: the per-domain table answers whatever it can (it is
~25x smaller); anything needing a client, login or subnet -- as a filter,
a grouping, or a distinct count -- reads the per-client table. Every event
is counted in exactly one row of each, so their sums always agree.

Ranges are matched at hour granularity: an hour bucket is included when it
starts inside [floor_hour(since), until].
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.branch_scope import BranchScope, branch_filter
from app.models.blocked_domain_aggregate import (
    BlockedDomainClientHourlyAggregate as C,
)
from app.models.blocked_domain_aggregate import (
    BlockedDomainHourlyAggregate as D,
)
from app.schemas.blocked_domains import (
    BlockGroupBy,
    BlockGroupRow,
    BlockGroupSort,
    BlockGroupsResponse,
    BlockKind,
    BlockSeriesPoint,
    BlockSummary,
)
from app.services.block_filters import BlockFilters

# Hard cap for an export -- a week has ~8k blocked domains, ~2k clients.
EXPORT_MAX_ROWS = 50_000
# Above this many keys, per-page lookups skip the IN (...) list (a driver
# bind-parameter limit) and read the filtered range instead.
_IN_LIST_MAX = 500
_CLIENT_ONLY_GROUPS = {"client", "user", "subnet"}

Table = type[D] | type[C]


def _floor_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _conditions(
    table: Table, since: datetime, until: datetime, branch: BranchScope, f: BlockFilters
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        table.bucket_ts >= _floor_hour(since),
        table.bucket_ts <= until,
    ]
    if branch:
        conditions.append(branch_filter(table.branch, branch))
    if f.proxy:
        conditions.append(table.proxy == f.proxy)
    if f.domains:
        domain_condition = f.domains.condition(table.domain)
        if domain_condition is not None:
            conditions.append(domain_condition)
    if table is C:
        if f.clients:
            conditions.append(f.clients.condition(C.client_ip))
        if f.users:
            conditions.append(f.users.condition(C.user))
    return conditions


def _has_kind(table: Table, kind: BlockKind) -> ColumnElement[bool]:
    if kind == "denied":
        return table.denied_count > 0
    if kind == "auth":
        return table.auth_count > 0
    return (table.denied_count + table.auth_count) > 0


def _measure(table: Table, kind: BlockKind):
    if kind == "denied":
        return func.sum(table.denied_count)
    if kind == "auth":
        return func.sum(table.auth_count)
    return func.sum(table.denied_count + table.auth_count)


def _distinct(table: Table, column, kind: BlockKind):
    """count(DISTINCT column) over rows with an event of the selected kind
    -- a CASE, not a WHERE, so the denied/auth sums stay whole."""
    return func.count(func.distinct(case((_has_kind(table, kind), column))))


def _key_column(table: Table, group: BlockGroupBy):
    return {
        "domain": table.domain,
        "branch": table.branch,
        "proxy": table.proxy,
        "client": C.client_ip,
        "user": C.user,
        "subnet": C.subnet,
    }[group]


def _pick_table(f: BlockFilters, group: BlockGroupBy | None = None, sort: str | None = None) -> Table:
    if f.needs_client_detail or group in _CLIENT_ONLY_GROUPS or sort in ("clients", "users"):
        return C
    return D


async def _groups(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: BranchScope,
    f: BlockFilters,
    *,
    group: BlockGroupBy,
    kind: BlockKind,
    sort: BlockGroupSort,
    limit: int,
    offset: int,
) -> tuple[list[BlockGroupRow], int]:
    table = _pick_table(f, group, sort)
    conditions = _conditions(table, since, until, branch, f)
    key = _key_column(table, group).label("key")
    measure = _measure(table, kind)
    denied = func.sum(table.denied_count).label("denied")
    auth = func.sum(table.auth_count).label("auth")
    first_seen = func.min(table.bucket_ts).label("first_seen")
    last_seen = func.max(table.bucket_ts).label("last_seen")
    domains = _distinct(table, table.domain, kind).label("domains")
    columns = [key, denied, auth, first_seen, last_seen, domains]
    if table is C:
        clients = _distinct(C, C.client_ip, kind).label("clients")
        users = _distinct(C, func.nullif(C.user, ""), kind).label("users")
        columns += [clients, users]
    else:
        clients = users = literal(0)

    grouped = select(*columns).where(*conditions).group_by(_key_column(table, group)).having(measure > 0)
    total = (await session.execute(select(func.count()).select_from(grouped.subquery()))).scalar_one()

    # Ties always break by key so a row never repeats or goes missing
    # across page boundaries.
    tie = key.asc()
    order = {
        "key": [tie],
        "last": [last_seen.desc(), measure.desc(), tie],
        "domains": [domains.desc(), measure.desc(), tie],
        "clients": [clients.desc(), measure.desc(), tie],
        "users": [users.desc(), measure.desc(), tie],
        "requests": [measure.desc(), tie],
    }[sort]
    page = (await session.execute(grouped.order_by(*order).limit(limit).offset(offset))).all()
    if not page:
        return [], total

    keys = [row.key for row in page]
    in_page = len(keys) <= _IN_LIST_MAX

    # Distinct clients/logins for a page grouped on the per-domain table come
    # from the per-client one (domain, branch and proxy exist on both).
    counts: dict[str, tuple[int, int]] = {}
    if table is D:
        c_key = _key_column(C, group)
        c_conditions = _conditions(C, since, until, branch, f)
        if in_page:
            c_conditions.append(c_key.in_(keys))
        counts = {
            row[0]: (row[1], row[2])
            for row in (
                await session.execute(
                    select(
                        c_key,
                        _distinct(C, C.client_ip, kind),
                        _distinct(C, func.nullif(C.user, ""), kind),
                    )
                    .where(*c_conditions)
                    .group_by(c_key)
                )
            ).all()
        }

    labels_where = [*conditions, _has_kind(table, kind)]
    if in_page:
        labels_where.append(_key_column(table, group).in_(keys))
    branches: dict[str, set[str]] = defaultdict(set)
    proxies: dict[str, set[str]] = defaultdict(set)
    for row_key, row_branch, row_proxy in (
        await session.execute(
            select(_key_column(table, group), table.branch, table.proxy).where(*labels_where).distinct()
        )
    ).all():
        branches[row_key].add(row_branch)
        if row_proxy:
            proxies[row_key].add(row_proxy)

    rows = []
    for row in page:
        client_count, user_count = counts.get(row.key, (0, 0)) if table is D else (row.clients, row.users)
        rows.append(
            BlockGroupRow(
                key=row.key,
                denied_count=row.denied or 0,
                auth_count=row.auth or 0,
                client_count=client_count,
                user_count=user_count,
                domain_count=row.domains,
                branches=sorted(branches[row.key]),
                proxies=sorted(proxies[row.key]),
                first_seen=row.first_seen,
                last_seen=row.last_seen,
            )
        )
    return rows, total


async def get_groups(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: BranchScope,
    f: BlockFilters,
    *,
    group: BlockGroupBy = "domain",
    kind: BlockKind = "denied",
    sort: BlockGroupSort = "requests",
    limit: int = 50,
    offset: int = 0,
) -> BlockGroupsResponse:
    rows, total = await _groups(
        session, since, until, branch, f, group=group, kind=kind, sort=sort, limit=limit, offset=offset
    )
    return BlockGroupsResponse(group=group, items=rows, total=total, limit=limit, offset=offset)


async def list_all_groups(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: BranchScope,
    f: BlockFilters,
    *,
    group: BlockGroupBy = "domain",
    kind: BlockKind = "denied",
    sort: BlockGroupSort = "requests",
) -> list[BlockGroupRow]:
    """Every matching group (up to EXPORT_MAX_ROWS), for the export."""
    rows, _ = await _groups(
        session, since, until, branch, f, group=group, kind=kind, sort=sort,
        limit=EXPORT_MAX_ROWS, offset=0,
    )
    return rows


async def _distinct_labels(
    session: AsyncSession, column, conditions: Sequence[ColumnElement[bool]]
) -> list[str]:
    values = (await session.execute(select(column).where(*conditions).distinct().order_by(column))).scalars()
    return [v for v in values if v]


async def get_summary(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: BranchScope,
    f: BlockFilters,
    *,
    kind: BlockKind = "denied",
) -> BlockSummary:
    table = _pick_table(f)
    conditions = _conditions(table, since, until, branch, f)
    denied, auth, domains = (
        await session.execute(
            select(
                func.coalesce(func.sum(table.denied_count), 0),
                func.coalesce(func.sum(table.auth_count), 0),
                _distinct(table, table.domain, kind),
            ).where(*conditions)
        )
    ).one()
    clients, users = (
        await session.execute(
            select(
                _distinct(C, C.client_ip, kind), _distinct(C, func.nullif(C.user, ""), kind)
            ).where(*_conditions(C, since, until, branch, f))
        )
    ).one()
    with_kind = [*conditions, _has_kind(table, kind)]
    series = [
        BlockSeriesPoint(bucket_ts=bucket, denied=d or 0, auth=a or 0)
        for bucket, d, a in (
            await session.execute(
                select(table.bucket_ts, func.sum(table.denied_count), func.sum(table.auth_count))
                .where(*conditions)
                .group_by(table.bucket_ts)
                .order_by(table.bucket_ts)
            )
        ).all()
    ]
    available = await _distinct_labels(
        session, D.proxy, _conditions(D, since, until, branch, BlockFilters())
    )
    return BlockSummary(
        domains=domains,
        denied=denied,
        auth=auth,
        clients=clients,
        users=users,
        branches=await _distinct_labels(session, table.branch, with_kind),
        proxies=await _distinct_labels(session, table.proxy, with_kind),
        series=series,
        available_proxies=available,
    )
