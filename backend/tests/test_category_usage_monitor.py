"""Tests for the daily non-work-category-time monitor
(app/services/category_usage_monitor.py)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.raw_event import RawEvent
from app.services import alert_settings_service
from app.services.category_usage_monitor import ANOMALY_TITLE, CategoryUsageMonitorJob


def _raw_event(client_ip: str, domain: str, timestamp: datetime) -> RawEvent:
    return RawEvent(
        timestamp=timestamp,
        duration_ms=1,
        client_ip=client_ip,
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url=f"http://{domain}/",
        domain=domain,
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=False,
    )


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    import app.services.category_usage_monitor as module

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db_session)


def _continuous_session(client_ip: str, domain: str, start: datetime, span_minutes: int) -> list[RawEvent]:
    """Events 20 minutes apart (well under SESSION_GAP_MINUTES=30) spanning
    `span_minutes`, so _summarize_sessions treats them as one continuous
    session of that duration rather than several zero-duration ones."""
    step = timedelta(minutes=20)
    count = span_minutes // 20 + 1
    return [_raw_event(client_ip, domain, start + i * step) for i in range(count)]


async def test_check_flags_client_over_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=60, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1), client_ip="10.0.0.30", user=None, request_count=1, blocked_count=0
        )
    )
    # 100 minutes of continuous browsing on a video-streaming domain (youtube.com).
    db_session.add_all(_continuous_session("10.0.0.30", "youtube.com", now - timedelta(hours=2), 100))
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert len(anomalies) == 1
    assert anomalies[0].client_ip == "10.0.0.30"


async def test_check_does_not_flag_client_under_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=120, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1), client_ip="10.0.0.31", user=None, request_count=1, blocked_count=0
        )
    )
    db_session.add_all(
        [
            _raw_event("10.0.0.31", "youtube.com", now - timedelta(hours=2)),
            _raw_event("10.0.0.31", "youtube.com", now - timedelta(hours=2) + timedelta(minutes=10)),
        ]
    )
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert anomalies == []


async def test_check_does_not_flag_work_category_time(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=30, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1), client_ip="10.0.0.32", user=None, request_count=1, blocked_count=0
        )
    )
    # github.com infers as work_tools -- shouldn't count toward the total,
    # even though this session (100 continuous minutes) would otherwise
    # clear the 30-minute threshold easily.
    db_session.add_all(_continuous_session("10.0.0.32", "github.com", now - timedelta(hours=2), 100))
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert anomalies == []


async def test_check_does_not_re_flag_within_the_same_day(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=60, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1), client_ip="10.0.0.33", user=None, request_count=1, blocked_count=0
        )
    )
    db_session.add_all(_continuous_session("10.0.0.33", "youtube.com", now - timedelta(hours=2), 100))
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()
    await job.check()  # simulate a second hourly tick on the same ongoing violation

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert len(anomalies) == 1


async def test_check_is_noop_when_threshold_disabled(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=0, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now - timedelta(hours=1), client_ip="10.0.0.34", user=None, request_count=1, blocked_count=0
        )
    )
    db_session.add_all(_continuous_session("10.0.0.34", "youtube.com", now - timedelta(hours=2), 100))
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert anomalies == []
