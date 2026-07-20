"""Tests for the daily non-work-category-time monitor
(app/services/category_usage_monitor.py).

Seeds client_category_minute_aggregates directly (what the monitor actually
reads, populated by Aggregator.flush() in production) rather than
raw_events -- see category_usage_monitor.py's module docstring for why the
monitor no longer reconstructs sessions from raw log lines.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_event import AnomalyEvent
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service
from app.services.category_usage_monitor import ANOMALY_TITLE, CategoryUsageMonitorJob


def _category_minutes(
    client_ip: str, category: DomainCategoryLabel, start: datetime, count: int
) -> list[ClientCategoryMinuteAggregate]:
    """`count` distinct one-minute buckets of activity in `category`,
    starting at `start` -- the monitor counts distinct buckets, so each
    entry here is one "minute spent"."""
    return [
        ClientCategoryMinuteAggregate(
            bucket_ts=start + timedelta(minutes=i),
            client_ip=client_ip,
            category=category,
            request_count=1,
            total_bytes=100,
        )
        for i in range(count)
    ]


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    import app.services.category_usage_monitor as module

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db_session)


async def test_check_flags_client_over_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=60, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    # 90 minutes of video-streaming activity -- comfortably over the 60-minute threshold.
    db_session.add_all(
        _category_minutes("10.0.0.30", DomainCategoryLabel.VIDEO_STREAMING, now - timedelta(hours=2), 90)
    )
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
    db_session.add_all(
        _category_minutes("10.0.0.31", DomainCategoryLabel.VIDEO_STREAMING, now - timedelta(hours=2), 2)
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
    # 100 minutes in work_tools -- exempt, so shouldn't count toward the
    # total even though it would otherwise clear the 30-minute threshold.
    db_session.add_all(
        _category_minutes("10.0.0.32", DomainCategoryLabel.WORK_TOOLS, now - timedelta(hours=2), 100)
    )
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
    db_session.add_all(
        _category_minutes("10.0.0.33", DomainCategoryLabel.VIDEO_STREAMING, now - timedelta(hours=2), 90)
    )
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
    db_session.add_all(
        _category_minutes("10.0.0.34", DomainCategoryLabel.VIDEO_STREAMING, now - timedelta(hours=2), 100)
    )
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert anomalies == []


async def test_check_combines_multiple_non_exempt_categories_for_the_same_minute(
    db_session: AsyncSession, monkeypatch
):
    """Activity in two different non-work categories within the *same*
    minute bucket counts as one active minute, not two -- distinct
    bucket_ts is what's counted, deliberately not summed per-category."""
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session, [], non_work_minutes_threshold=10, client_daily_byte_quota_bytes=None
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=2)
    db_session.add_all(_category_minutes("10.0.0.35", DomainCategoryLabel.VIDEO_STREAMING, start, 5))
    db_session.add_all(_category_minutes("10.0.0.35", DomainCategoryLabel.SOCIAL_MEDIA, start, 5))
    await db_session.commit()

    job = CategoryUsageMonitorJob()
    await job.check()

    # 5 overlapping minutes across two categories == 5 active minutes, still
    # under the 10-minute threshold.
    anomalies = (
        await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE))
    ).scalars().all()
    assert anomalies == []
