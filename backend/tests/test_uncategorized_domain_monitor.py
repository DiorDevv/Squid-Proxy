"""Tests for the high-traffic-uncategorized-domain monitor
(app/services/uncategorized_domain_monitor.py). Seeds domain_minute_aggregates
directly (what stats_service.get_top_domains actually reads) rather than
raw_events, matching test_category_usage_monitor.py's approach for its
equivalent aggregate table."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_event import AnomalyEvent
from app.models.domain_aggregate import DomainMinuteAggregate
from app.services import alert_settings_service
from app.services.uncategorized_domain_monitor import ANOMALY_TITLE, UncategorizedDomainMonitorJob


def _domain_minutes(
    domain: str, start: datetime, count: int, branch: str = "default"
) -> list[DomainMinuteAggregate]:
    return [
        DomainMinuteAggregate(
            bucket_ts=start + timedelta(minutes=i),
            domain=domain,
            branch=branch,
            request_count=1,
            blocked_count=0,
            total_bytes=100,
        )
        for i in range(count)
    ]


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    import app.services.uncategorized_domain_monitor as module

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db_session)


async def _anomalies(db_session: AsyncSession) -> list[AnomalyEvent]:
    return (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )


async def test_check_flags_domain_over_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        uncategorized_domain_request_threshold=50,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add_all(_domain_minutes("mystery-site.example", now - timedelta(hours=2), 60))
    await db_session.commit()

    await UncategorizedDomainMonitorJob().run()

    anomalies = await _anomalies(db_session)
    assert len(anomalies) == 1
    assert anomalies[0].domain == "mystery-site.example"
    assert anomalies[0].kind == "uncategorized_domain_high_traffic"
    assert anomalies[0].params == {"domain": "mystery-site.example", "requests": 60, "threshold": 50}


async def test_check_does_not_flag_domain_under_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        uncategorized_domain_request_threshold=100,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add_all(_domain_minutes("quiet-site.example", now - timedelta(hours=2), 10))
    await db_session.commit()

    await UncategorizedDomainMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_is_noop_when_threshold_not_configured(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        uncategorized_domain_request_threshold=None,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add_all(_domain_minutes("busy-site.example", now - timedelta(hours=2), 1000))
    await db_session.commit()

    await UncategorizedDomainMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_categorized_domain_is_never_flagged(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        uncategorized_domain_request_threshold=10,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    # netflix.com is in the curated known-hostname list (video_streaming),
    # so it must never show up as "uncategorized" no matter how much
    # traffic it has.
    db_session.add_all(_domain_minutes("netflix.com", now - timedelta(hours=2), 100))
    await db_session.commit()

    await UncategorizedDomainMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_does_not_re_flag_within_cooldown(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        uncategorized_domain_request_threshold=50,
        actor_user_id="actor-1",
    )
    now = datetime.now(UTC)
    db_session.add_all(_domain_minutes("repeat-offender.example", now - timedelta(hours=2), 60))
    await db_session.commit()

    job = UncategorizedDomainMonitorJob()
    await job.run()
    await job.run()  # simulates the next day's check while still over threshold

    assert len(await _anomalies(db_session)) == 1
