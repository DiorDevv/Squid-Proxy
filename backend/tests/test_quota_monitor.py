"""Tests for the client daily data-quota monitor
(app/services/quota_monitor.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.models.client_aggregate import ClientMinuteAggregate
from app.services import alert_settings_service, telegram_alerting
from app.services.quota_monitor import ANOMALY_TITLE, QuotaMonitorJob

ONE_GB = 1_000_000_000


@pytest.fixture(autouse=True)
def _disable_telegram_channel(monkeypatch):
    """job.run() below flows into maybe_alert(), which fans out to
    telegram_alerting.notify() alongside the anomaly persistence this file
    actually tests -- without this, whether these tests hit a real DB
    depends on whatever TELEGRAM_BOT_TOKEN happens to be set in the
    environment (e.g. a real .env for local manual testing), unrelated to
    what this file is testing."""
    monkeypatch.setattr(telegram_alerting, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN=None))


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    import app.services.quota_monitor as module

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db_session)


async def test_check_flags_client_over_quota(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=5 * ONE_GB,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1),
            client_ip="10.0.0.40",
            user=None,
            request_count=1,
            blocked_count=0,
            total_bytes=6 * ONE_GB,
        )
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert len(anomalies) == 1
    assert anomalies[0].client_ip == "10.0.0.40"
    assert anomalies[0].severity == AnomalySeverity.HIGH


async def test_check_uses_critical_severity_at_double_quota(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=5 * ONE_GB,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1),
            client_ip="10.0.0.41",
            user=None,
            request_count=1,
            blocked_count=0,
            total_bytes=12 * ONE_GB,
        )
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert anomalies[0].severity == AnomalySeverity.CRITICAL


async def test_check_does_not_flag_client_under_quota(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=5 * ONE_GB,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1),
            client_ip="10.0.0.42",
            user=None,
            request_count=1,
            blocked_count=0,
            total_bytes=1 * ONE_GB,
        )
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert anomalies == []


async def test_check_is_noop_when_quota_not_configured(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    # No alert_settings row at all -- default is "no quota configured".
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1),
            client_ip="10.0.0.43",
            user=None,
            request_count=1,
            blocked_count=0,
            total_bytes=999 * ONE_GB,
        )
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert anomalies == []


async def test_check_compares_each_branch_against_its_own_quota(db_session: AsyncSession, monkeypatch):
    """Same client_ip active in two branches: branch A has a quota configured
    and is over it, branch B has no quota configured at all -- only branch
    A's usage should be flagged, proving thresholds aren't shared globally
    across branches."""
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=5 * ONE_GB,
        branch="hq",
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=now - timedelta(hours=1),
                client_ip="10.0.0.50",
                branch="hq",
                user=None,
                request_count=1,
                blocked_count=0,
                total_bytes=6 * ONE_GB,
            ),
            ClientMinuteAggregate(
                bucket_ts=now - timedelta(hours=1),
                client_ip="10.0.0.50",
                branch="branch-office",
                user=None,
                request_count=1,
                blocked_count=0,
                total_bytes=6 * ONE_GB,
            ),
        ]
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert len(anomalies) == 1
    assert anomalies[0].branch == "hq"


async def test_check_does_not_re_flag_within_the_same_day(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=5 * ONE_GB,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1),
            client_ip="10.0.0.44",
            user=None,
            request_count=1,
            blocked_count=0,
            total_bytes=6 * ONE_GB,
        )
    )
    await db_session.commit()

    job = QuotaMonitorJob()
    await job.run()
    await job.run()  # simulate a second hourly tick on the same ongoing overage

    anomalies = (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )
    assert len(anomalies) == 1
