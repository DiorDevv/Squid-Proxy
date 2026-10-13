"""The Blocked page: the hourly aggregates the aggregator fills (403 vs 407,
per proxy / client / login), the shared filter language, the Analysis
view's summary and grouped list built on them, its export, and the same
filters on the raw-events Requests view."""

import dataclasses
import io
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.blocked_domain_aggregate import (
    BlockedDomainClientHourlyAggregate,
    BlockedDomainHourlyAggregate,
)
from app.models.raw_event import RawEvent
from app.services import blocked_analysis_service as svc
from app.services.aggregator import Aggregator
from app.services.block_filters import FilterError, parse_clients, parse_filters, subnet_of
from app.services.event_store import RingBuffer
from app.services.log_parser import parse_line

HOUR = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
NOW = datetime.now(UTC)
SINCE = NOW - timedelta(hours=24)
NO_FILTERS = parse_filters(None, None, None, None)


# --- filter language -------------------------------------------------------


def test_cidr_expands_to_octet_prefixes():
    assert parse_clients("172.25.108.0/22").prefixes == (
        "172.25.108.", "172.25.109.", "172.25.110.", "172.25.111.",
    )
    assert parse_clients("10.0.0.0/8").prefixes == ("10.",)
    assert parse_clients("10.0.0.7/32").exact == ("10.0.0.7",)
    assert parse_clients("172.25.103.*, 172.25.104.").prefixes == ("172.25.103.", "172.25.104.")
    with pytest.raises(FilterError):
        parse_clients("not-an-ip")
    assert len(parse_clients("10.0.0.0/4").prefixes) == 16  # 10. .. 15.
    with pytest.raises(FilterError):
        parse_clients("fd00::/8")


def test_subnet_of():
    assert subnet_of("172.25.110.207") == "172.25.110.0/24"
    assert subnet_of("::1") == "::1"


# --- aggregator ------------------------------------------------------------


def _line(domain: str, client_ip: str, status: str, user: str = "-") -> str:
    return f"1737100800.123 45 {client_ip} {status} 0 GET http://{domain}/ {user} HIER_NONE/- -"


async def test_flush_splits_denied_and_login_per_hour_proxy_client_and_user(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)

    def via77(line):
        return dataclasses.replace(parse_line(line), proxy="172.25.42.77")

    ring_buffer.append(via77(_line("ctldl.windowsupdate.com", "10.0.0.1", "TCP_DENIED/403")))
    ring_buffer.append(via77(_line("ctldl.windowsupdate.com", "10.0.0.1", "TCP_DENIED/403", user="alice")))
    ring_buffer.append(via77(_line("ctldl.windowsupdate.com", "10.0.0.2", "TCP_DENIED/407")))
    ring_buffer.append(parse_line(_line("ctldl.windowsupdate.com", "10.0.0.3", "TCP_DENIED/403")))
    ring_buffer.append(parse_line(_line("allowed.example", "10.0.0.1", "TCP_MISS/200")))
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    await aggregator.flush()
    # A second flush into the same hour adds to the rows, not replaces them.
    ring_buffer.append(via77(_line("ctldl.windowsupdate.com", "10.0.0.1", "TCP_DENIED/403")))
    await aggregator.flush()

    async with session_factory() as session:
        domain_rows = {
            row.proxy: row
            for row in (await session.execute(select(BlockedDomainHourlyAggregate))).scalars()
        }
        assert set(domain_rows) == {"172.25.42.77", ""}  # unlabeled source stored as ""
        assert (domain_rows["172.25.42.77"].denied_count, domain_rows["172.25.42.77"].auth_count) == (3, 1)
        assert (domain_rows[""].denied_count, domain_rows[""].auth_count) == (1, 0)
        assert domain_rows[""].bucket_ts.replace(tzinfo=UTC) == datetime(2025, 1, 17, 8, tzinfo=UTC)

        client_rows = {
            (row.client_ip, row.user): (row.denied_count, row.auth_count, row.subnet)
            for row in (await session.execute(select(BlockedDomainClientHourlyAggregate))).scalars()
        }
        assert client_rows == {
            ("10.0.0.1", ""): (2, 0, "10.0.0.0/24"),
            ("10.0.0.1", "alice"): (1, 0, "10.0.0.0/24"),
            ("10.0.0.2", ""): (0, 1, "10.0.0.0/24"),
            ("10.0.0.3", ""): (1, 0, "10.0.0.0/24"),
        }


# --- analysis --------------------------------------------------------------

# (hours ago from HOUR, branch, proxy, domain, client, login, denied, auth)
_EVENTS = [
    (0, "main", "172.25.42.77", "crl.usertrust.com", "10.0.0.1", "", 50, 0),
    (0, "main", "172.25.42.77", "crl.usertrust.com", "10.0.0.2", "bob", 40, 10),
    (1, "filial", "", "crl.usertrust.com", "10.0.1.3", "", 10, 0),
    (0, "main", "172.25.42.24", "crl.sectigo.com", "10.0.0.1", "", 60, 0),
    # login-only: not a block, so absent from the default list
    (0, "main", "172.25.42.24", "crl.apple.com", "10.0.0.9", "carol", 0, 6),
    (0, "filial", "", "ctldl.windowsupdate.com", "10.0.1.4", "", 500, 0),
    (0, "filial", "", "ctldl.windowsupdate.com", "10.0.1.5", "", 100, 0),
    (0, "main", "", "www.microsoft.com", "10.0.0.1", "", 5, 0),
    # outside the 24h range
    (72, "main", "", "old.example", "10.0.0.1", "", 999, 0),
]


async def _seed(db: AsyncSession) -> None:
    domains: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for ago, branch, proxy, domain, ip, user, denied, auth in _EVENTS:
        hour = HOUR - timedelta(hours=ago)
        db.add(BlockedDomainClientHourlyAggregate(
            bucket_ts=hour, branch=branch, proxy=proxy, domain=domain, client_ip=ip, user=user,
            subnet=subnet_of(ip), denied_count=denied, auth_count=auth,
        ))
        counts = domains[(hour, branch, proxy, domain)]
        counts[0] += denied
        counts[1] += auth
    for (hour, branch, proxy, domain), (denied, auth) in domains.items():
        db.add(BlockedDomainHourlyAggregate(
            bucket_ts=hour, branch=branch, proxy=proxy, domain=domain, denied_count=denied, auth_count=auth
        ))
    await db.commit()


async def _groups(db, *, domains=None, clients=None, users=None, proxy=None, branch=None, **kwargs):
    f = parse_filters(domains, clients, users, proxy)
    return await svc.get_groups(db, SINCE, NOW, branch, f, **kwargs)


async def test_default_groups_by_domain_real_blocks_only(db_session: AsyncSession):
    await _seed(db_session)
    result = await _groups(db_session)
    assert [r.key for r in result.items] == [
        "ctldl.windowsupdate.com", "crl.usertrust.com", "crl.sectigo.com", "www.microsoft.com",
    ]
    usertrust = result.items[1]
    assert (usertrust.denied_count, usertrust.auth_count) == (100, 10)
    assert (usertrust.client_count, usertrust.user_count, usertrust.domain_count) == (3, 1, 1)
    assert usertrust.branches == ["filial", "main"]
    assert usertrust.proxies == ["172.25.42.77"]
    assert usertrust.first_seen < usertrust.last_seen


async def test_domain_patterns(db_session: AsyncSession):
    await _seed(db_session)
    contains = await _groups(db_session, domains="crl.", kind="all")
    assert {r.key for r in contains.items} == {"crl.usertrust.com", "crl.sectigo.com", "crl.apple.com"}
    wildcard = await _groups(db_session, domains="*.microsoft.com, ctldl.*")
    assert {r.key for r in wildcard.items} == {"www.microsoft.com", "ctldl.windowsupdate.com"}
    excluded = await _groups(db_session, domains="!*.microsoft.com !ctldl.*")
    assert {r.key for r in excluded.items} == {"crl.usertrust.com", "crl.sectigo.com"}
    exact = await _groups(db_session, domains="=CRL.usertrust.com, =usertrust.com")
    assert [r.key for r in exact.items] == ["crl.usertrust.com"]


async def test_group_by_client_user_subnet_with_filters(db_session: AsyncSession):
    await _seed(db_session)
    clients = await _groups(db_session, group="client", domains="crl.")
    assert [(r.key, r.denied_count, r.domain_count) for r in clients.items] == [
        ("10.0.0.1", 110, 2), ("10.0.0.2", 40, 1), ("10.0.1.3", 10, 1),
    ]
    subnets = await _groups(db_session, group="subnet")
    assert [(r.key, r.client_count, r.domain_count) for r in subnets.items] == [
        ("10.0.1.0/24", 3, 2), ("10.0.0.0/24", 2, 3),
    ]
    users = await _groups(db_session, group="user", kind="all")
    assert {r.key: r.client_count for r in users.items} == {"": 4, "bob": 1, "carol": 1}

    # CIDR / login filters narrow everything, including the domain grouping
    in_subnet = await _groups(db_session, clients="10.0.1.0/24")
    assert [(r.key, r.client_count) for r in in_subnet.items] == [
        ("ctldl.windowsupdate.com", 2), ("crl.usertrust.com", 1),
    ]
    bob = await _groups(db_session, users="bob", kind="all")
    assert [(r.key, r.denied_count, r.auth_count) for r in bob.items] == [("crl.usertrust.com", 40, 10)]
    no_login = await _groups(db_session, users="-", domains="crl.usertrust")
    assert [r.denied_count for r in no_login.items] == [60]


async def test_branch_proxy_groups_sort_and_paging(db_session: AsyncSession):
    await _seed(db_session)
    proxies = await _groups(db_session, group="proxy")
    # "" = sources without a proxy label (the filial here)
    assert [(r.key, r.denied_count, r.client_count) for r in proxies.items] == [
        ("", 615, 4), ("172.25.42.77", 90, 2), ("172.25.42.24", 60, 1),
    ]
    by_clients = await _groups(db_session, sort="clients")
    assert by_clients.items[0].key == "crl.usertrust.com"

    seen = []
    for offset in (0, 2):
        page = await _groups(db_session, limit=2, offset=offset)
        assert page.total == 4
        seen += [r.key for r in page.items]
    assert seen == ["ctldl.windowsupdate.com", "crl.usertrust.com", "crl.sectigo.com", "www.microsoft.com"]

    filial = await _groups(db_session, branch="filial")
    assert [(r.key, r.denied_count) for r in filial.items] == [
        ("ctldl.windowsupdate.com", 600), ("crl.usertrust.com", 10),
    ]


async def test_summary(db_session: AsyncSession):
    await _seed(db_session)
    s = await svc.get_summary(db_session, SINCE, NOW, None, parse_filters("crl.", None, None, None))
    assert (s.domains, s.denied, s.auth, s.clients, s.users) == (2, 160, 16, 3, 1)
    assert s.branches == ["filial", "main"]
    assert s.proxies == ["172.25.42.24", "172.25.42.77"]
    assert sum(p.denied for p in s.series) == 160 and len(s.series) == 2
    assert s.available_proxies == ["172.25.42.24", "172.25.42.77"]

    by_login = await svc.get_summary(db_session, SINCE, NOW, None, parse_filters(None, None, "bob", None))
    assert (by_login.domains, by_login.denied, by_login.clients, by_login.users) == (1, 40, 1, 1)


# --- routes ----------------------------------------------------------------


async def test_routes(app_client: AsyncClient, viewer_token, auth_headers, db_session):
    await _seed(db_session)
    headers = auth_headers(viewer_token)
    summary = await app_client.get("/api/blocked/summary", params={"range": "24h", "domains": "crl."}, headers=headers)
    assert summary.status_code == 200
    assert summary.json()["clients"] == 3

    groups = await app_client.get(
        "/api/blocked/groups", params={"range": "24h", "group": "client", "domains": "crl."}, headers=headers
    )
    assert [row["key"] for row in groups.json()["items"]] == ["10.0.0.1", "10.0.0.2", "10.0.1.3"]

    bad = await app_client.get("/api/blocked/groups", params={"clients": "nope"}, headers=headers)
    assert bad.status_code == 422
    assert "not an IP" in bad.json()["detail"]


async def test_targeted_lookup_is_audited(app_client: AsyncClient, admin_token, auth_headers, db_session):
    await _seed(db_session)
    await app_client.get("/api/blocked/groups", params={"range": "24h"}, headers=auth_headers(admin_token))
    await app_client.get(
        "/api/blocked/groups", params={"range": "24h", "clients": "10.0.1.0/24"}, headers=auth_headers(admin_token)
    )
    entries = (
        await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EVENT_SEARCH_RUN))
    ).scalars().all()
    assert [e.detail for e in entries] == ["blocked-analysis group=domain clients=10.0.1."]


async def test_export_keys_only(app_client: AsyncClient, admin_token, auth_headers, db_session):
    await _seed(db_session)
    response = await app_client.get(
        "/api/blocked/groups/export",
        params={"range": "24h", "format": "csv", "columns": "key", "group": "client", "domains": "crl."},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.content.decode("utf-8").splitlines() == ["10.0.0.1", "10.0.0.2", "10.0.1.3"]
    entries = (
        await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EXPORT_CREATED))
    ).scalars().all()
    assert [e.detail for e in entries] == [
        "blocked-client format=csv columns=key kind=denied rows=3 domains=crl."
    ]


async def test_export_xlsx(app_client: AsyncClient, admin_token, auth_headers, db_session):
    await _seed(db_session)
    response = await app_client.get(
        "/api/blocked/groups/export",
        params={"range": "24h", "format": "xlsx", "lang": "uz", "domains": "crl."},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert 'filename="bloklangan-domain-barcha-' in response.headers["content-disposition"]
    book = load_workbook(io.BytesIO(response.content))
    values = list(book["Domen"].iter_rows(values_only=True))
    assert values[0][1] == "Domen"
    assert [v[1] for v in values[1:]] == ["crl.usertrust.com", "crl.sectigo.com"]
    assert values[1][2:7] == (100, 10, 3, 1, 1)
    info = {row[0]: row[1] for row in book["Ma'lumot"].iter_rows(values_only=True)}
    assert info["domains"] == "crl."


async def test_export_is_not_for_viewers(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get(
        "/api/blocked/groups/export", params={"range": "24h"}, headers=auth_headers(viewer_token)
    )
    assert response.status_code == 403


# --- the raw-events Requests view takes the same filters -------------------


def _raw(domain: str, status: int, client_ip: str = "10.0.0.1", user: str | None = None) -> RawEvent:
    return RawEvent(
        timestamp=datetime.now(UTC), duration_ms=1, client_ip=client_ip, action="TCP_DENIED",
        status_code=status, bytes=0, method="GET", url=f"http://{domain}/", domain=domain,
        user=user, blocked=True,
    )


async def test_events_block_kind_and_shared_filters(app_client: AsyncClient, admin_token, auth_headers, db_session):
    db_session.add_all([
        _raw("crl.usertrust.com", 403),
        _raw("login.example", 407),
        _raw("crl.sectigo.com", 403, client_ip="10.0.1.7", user="bob"),
    ])
    await db_session.commit()

    async def domains(**params):
        response = await app_client.get(
            "/api/events", params={"blocked_only": "true", **params}, headers=auth_headers(admin_token)
        )
        assert response.status_code == 200
        return sorted(item["domain"] for item in response.json()["items"])

    assert await domains() == ["crl.sectigo.com", "crl.usertrust.com", "login.example"]
    assert await domains(block_kind="denied") == ["crl.sectigo.com", "crl.usertrust.com"]
    assert await domains(block_kind="auth") == ["login.example"]
    assert await domains(domains="crl.*", clients="10.0.1.0/24") == ["crl.sectigo.com"]
    assert await domains(users="-", block_kind="denied") == ["crl.usertrust.com"]
