"""Tests for the watchlist feature: CRUD service, the monitor job that
raises an anomaly on a hit, and the admin-only API + branch scoping."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.watchlist_entry import WatchlistEntry, WatchlistTargetType
from app.services import watchlist_service
from app.services.watchlist_monitor import WatchlistMonitorJob

NOW = datetime.now(UTC).replace(second=0, microsecond=0)


# --- service ---------------------------------------------------------------


async def test_create_normalizes_and_rejects_duplicates(db_session: AsyncSession):
    a = await watchlist_service.create_entry(
        db_session, WatchlistTargetType.DOMAIN, "  Bet365.COM ", "note", "", "actor-1"
    )
    assert a.value == "bet365.com"

    with pytest.raises(watchlist_service.WatchlistConflict):
        await watchlist_service.create_entry(
            db_session, WatchlistTargetType.DOMAIN, "bet365.com", None, "", "actor-1"
        )


async def test_list_is_branch_scoped(db_session: AsyncSession):
    await watchlist_service.create_entry(
        db_session, WatchlistTargetType.CLIENT_IP, "10.0.0.1", None, "", "a"
    )
    await watchlist_service.create_entry(
        db_session, WatchlistTargetType.CLIENT_IP, "10.0.0.2", None, "hq", "a"
    )
    await watchlist_service.create_entry(
        db_session, WatchlistTargetType.CLIENT_IP, "10.0.0.3", None, "warehouse", "a"
    )

    unrestricted = await watchlist_service.list_entries(db_session, branch=None)
    assert {e.value for e in unrestricted} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}

    hq_only = await watchlist_service.list_entries(db_session, branch="hq")
    assert {e.value for e in hq_only} == {"10.0.0.1", "10.0.0.2"}  # "" (any) + hq


# --- monitor -------------------------------------------------------------


async def _run_monitor(db_engine, monkeypatch) -> list[AnomalyEvent]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.watchlist_monitor as mod

    monkeypatch.setattr(mod, "AsyncSessionLocal", session_factory)
    alerts: list[AnomalyEvent] = []

    async def _fake_alert(row: AnomalyEvent) -> None:
        alerts.append(row)

    monkeypatch.setattr(mod, "maybe_alert", _fake_alert)
    await WatchlistMonitorJob(interval_seconds=300).run()
    return alerts


async def test_monitor_raises_anomaly_for_active_watched_domain(db_engine, db_session, monkeypatch):
    db_session.add_all(
        [
            WatchlistEntry(target_type=WatchlistTargetType.DOMAIN, value="pokerstars.com", branch="", created_by="a"),
            DomainMinuteAggregate(
                bucket_ts=NOW - timedelta(minutes=1), domain="pokerstars.com", branch="default",
                request_count=7, blocked_count=3, total_bytes=100,
            ),
        ]
    )
    await db_session.commit()

    alerts = await _run_monitor(db_engine, monkeypatch)
    assert len(alerts) == 1
    assert alerts[0].kind == "watchlist_hit"
    assert alerts[0].severity == AnomalySeverity.HIGH  # blocked > 0
    assert alerts[0].domain == "pokerstars.com"

    row = (
        await db_session.execute(select(WatchlistEntry).where(WatchlistEntry.value == "pokerstars.com"))
    ).scalar_one()
    await db_session.refresh(row)
    assert row.last_seen_at is not None
    assert row.last_alerted_at is not None


async def test_monitor_respects_cooldown(db_engine, db_session, monkeypatch):
    db_session.add_all(
        [
            WatchlistEntry(
                target_type=WatchlistTargetType.CLIENT_IP, value="10.9.9.9", branch="", created_by="a",
                last_alerted_at=NOW - timedelta(minutes=5),  # within the 1h default cooldown
            ),
            ClientMinuteAggregate(
                bucket_ts=NOW - timedelta(minutes=1), client_ip="10.9.9.9", branch="default", user=None,
                request_count=4, blocked_count=0, total_bytes=10,
            ),
        ]
    )
    await db_session.commit()

    alerts = await _run_monitor(db_engine, monkeypatch)
    assert alerts == []  # cooldown suppresses it
    # but last_seen_at is still refreshed
    row = (
        await db_session.execute(select(WatchlistEntry).where(WatchlistEntry.value == "10.9.9.9"))
    ).scalar_one()
    await db_session.refresh(row)
    assert row.last_seen_at is not None


async def test_monitor_matches_domain_case_insensitively(db_engine, db_session, monkeypatch):
    """The watchlist value is stored lower-cased; the aggregates keep
    whatever case Squid logged. A watched "Evil.Example" must still fire on
    logged "evil.example" (and vice versa)."""
    db_session.add_all(
        [
            WatchlistEntry(
                target_type=WatchlistTargetType.DOMAIN, value="evil.example", branch="", created_by="a"
            ),
            DomainMinuteAggregate(
                bucket_ts=NOW - timedelta(minutes=1), domain="Evil.Example", branch="default",
                request_count=3, blocked_count=0, total_bytes=10,
            ),
        ]
    )
    await db_session.commit()

    alerts = await _run_monitor(db_engine, monkeypatch)
    assert len(alerts) == 1
    assert alerts[0].kind == "watchlist_hit"


async def test_monitor_ignores_inactive_and_quiet_targets(db_engine, db_session, monkeypatch):
    db_session.add_all(
        [
            WatchlistEntry(target_type=WatchlistTargetType.DOMAIN, value="quiet.example", branch="", created_by="a"),
            WatchlistEntry(
                target_type=WatchlistTargetType.DOMAIN, value="busy.example", branch="", created_by="a", active=False
            ),
            DomainMinuteAggregate(
                bucket_ts=NOW - timedelta(minutes=1), domain="busy.example", branch="default",
                request_count=99, blocked_count=0, total_bytes=100,
            ),
        ]
    )
    await db_session.commit()

    alerts = await _run_monitor(db_engine, monkeypatch)
    assert alerts == []


# --- API -----------------------------------------------------------------


async def test_watchlist_api_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    resp = await app_client.get("/api/watchlist", headers=auth_headers(viewer_token))
    assert resp.status_code == 403


async def test_watchlist_api_crud_roundtrip(app_client: AsyncClient, admin_token, auth_headers):
    create = await app_client.post(
        "/api/watchlist",
        headers=auth_headers(admin_token),
        json={"target_type": "domain", "value": "Evil.example", "note": "suspicious"},
    )
    assert create.status_code == 201
    entry = create.json()
    assert entry["value"] == "evil.example"

    dup = await app_client.post(
        "/api/watchlist",
        headers=auth_headers(admin_token),
        json={"target_type": "domain", "value": "evil.example"},
    )
    assert dup.status_code == 409

    listed = await app_client.get("/api/watchlist", headers=auth_headers(admin_token))
    assert [e["value"] for e in listed.json()] == ["evil.example"]

    patched = await app_client.patch(
        f"/api/watchlist/{entry['id']}", headers=auth_headers(admin_token), json={"active": False}
    )
    assert patched.status_code == 200 and patched.json()["active"] is False

    deleted = await app_client.delete(
        f"/api/watchlist/{entry['id']}", headers=auth_headers(admin_token)
    )
    assert deleted.status_code == 204
    assert (await app_client.get("/api/watchlist", headers=auth_headers(admin_token))).json() == []


async def test_branch_admin_cannot_watch_another_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    resp = await app_client.post(
        "/api/watchlist",
        headers=auth_headers(branch_a_admin_token),
        json={"target_type": "client_ip", "value": "10.0.0.1", "branch": "branch-b"},
    )
    assert resp.status_code == 403
