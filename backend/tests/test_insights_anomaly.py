"""Unit tests for StatisticalAnomalyProvider, run directly against the
in-memory test DB (db_session fixture) so historical-baseline queries hit a
real table rather than a mock."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.anomaly import StatisticalAnomalyProvider
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import alert_settings_service
from app.services.log_parser import ParsedEvent

WINDOW_START = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)


def _event(
    client_ip: str = "10.0.0.5",
    domain: str | None = "example.com",
    blocked: bool = False,
    timestamp: datetime = WINDOW_START,
) -> ParsedEvent:
    return ParsedEvent(
        timestamp=timestamp,
        duration_ms=10,
        client_ip=client_ip,
        action="TCP_DENIED" if blocked else "TCP_MISS",
        status_code=403 if blocked else 200,
        bytes=100,
        method="GET",
        url=f"http://{domain}/",
        domain=domain,
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=blocked,
    )


async def _seed_minute_history(session: AsyncSession, count: int, total_requests: int) -> None:
    for i in range(count):
        bucket = WINDOW_START - timedelta(minutes=i + 1)
        session.add(
            MinuteAggregate(
                bucket_ts=bucket,
                total_requests=total_requests,
                blocked_requests=0,
                allowed_requests=total_requests,
                total_bytes=0,
            )
        )
    await session.commit()


async def test_traffic_spike_flagged_when_current_window_far_exceeds_baseline(db_session: AsyncSession):
    await _seed_minute_history(db_session, count=6, total_requests=10)
    events = [_event() for _ in range(40)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    spikes = [a for a in anomalies if a.title == "Traffic spike detected"]
    assert len(spikes) == 1


async def test_traffic_spike_not_flagged_without_enough_history(db_session: AsyncSession):
    await _seed_minute_history(db_session, count=2, total_requests=10)
    events = [_event() for _ in range(100)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_traffic_spike_not_flagged_for_ordinary_traffic(db_session: AsyncSession):
    await _seed_minute_history(db_session, count=6, total_requests=10)
    events = [_event() for _ in range(12)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_new_blocked_domain_is_flagged(db_session: AsyncSession):
    events = [_event(domain="evil.example", blocked=True)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    new_domain_anomalies = [a for a in anomalies if a.title == "New blocked domain observed"]
    assert len(new_domain_anomalies) == 1
    assert new_domain_anomalies[0].domain == "evil.example"


async def test_previously_seen_blocked_domain_is_not_flagged(db_session: AsyncSession):
    db_session.add(
        DomainMinuteAggregate(
            bucket_ts=WINDOW_START - timedelta(hours=1),
            domain="known.example",
            request_count=5,
            blocked_count=1,
        )
    )
    await db_session.commit()

    events = [_event(domain="known.example", blocked=True)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "New blocked domain observed"]


async def test_allowed_traffic_never_triggers_new_domain_check(db_session: AsyncSession):
    events = [_event(domain="brand-new.example", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "New blocked domain observed"]


async def test_client_mostly_blocked_is_flagged(db_session: AsyncSession):
    events = [_event(client_ip="10.0.0.9", blocked=True) for _ in range(4)] + [
        _event(client_ip="10.0.0.9", blocked=False)
    ]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    client_anomalies = [a for a in anomalies if a.title == "Client mostly blocked"]
    assert len(client_anomalies) == 1
    assert client_anomalies[0].client_ip == "10.0.0.9"


async def test_client_blocked_ratio_below_threshold_is_not_flagged(db_session: AsyncSession):
    events = [_event(client_ip="10.0.0.9", blocked=True)] + [
        _event(client_ip="10.0.0.9", blocked=False) for _ in range(9)
    ]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Client mostly blocked"]


async def test_client_below_minimum_requests_is_not_flagged_even_if_all_blocked(db_session: AsyncSession):
    events = [_event(client_ip="10.0.0.9", blocked=True) for _ in range(3)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Client mostly blocked"]


async def test_no_events_returns_no_anomalies(db_session: AsyncSession):
    anomalies = await StatisticalAnomalyProvider().detect_anomalies([], db_session)
    assert anomalies == []


async def test_sensitive_category_first_visit_is_flagged(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session, [DomainCategoryLabel.GAMBLING], non_work_minutes_threshold=120, client_daily_byte_quota_bytes=None
    )
    events = [_event(client_ip="10.0.0.20", domain="gambling-paradise.bet", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    flagged = [a for a in anomalies if a.title == "Sensitive category visited"]
    assert len(flagged) == 1
    assert flagged[0].client_ip == "10.0.0.20"
    assert flagged[0].domain == "gambling-paradise.bet"


async def test_sensitive_category_visit_not_flagged_when_no_categories_configured(db_session: AsyncSession):
    # No alert_settings row at all -- default is "nothing configured".
    events = [_event(client_ip="10.0.0.21", domain="gambling-paradise.bet", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited"]


async def test_sensitive_category_visit_not_flagged_for_uninvolved_category(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session, [DomainCategoryLabel.GAMBLING], non_work_minutes_threshold=120, client_daily_byte_quota_bytes=None
    )
    events = [_event(client_ip="10.0.0.22", domain="github.com", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited"]


async def test_sensitive_category_repeat_visit_is_not_flagged(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session, [DomainCategoryLabel.GAMBLING], non_work_minutes_threshold=120, client_daily_byte_quota_bytes=None
    )
    db_session.add(
        RawEvent(
            timestamp=WINDOW_START - timedelta(hours=1),
            duration_ms=1,
            client_ip="10.0.0.23",
            action="TCP_MISS",
            status_code=200,
            bytes=100,
            method="GET",
            url="http://gambling-paradise.bet/",
            domain="gambling-paradise.bet",
            user=None,
            hierarchy=None,
            peer=None,
            content_type=None,
            blocked=False,
        )
    )
    await db_session.commit()

    events = [_event(client_ip="10.0.0.23", domain="gambling-paradise.bet", blocked=False)]
    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited"]


async def test_one_wildly_out_of_order_event_does_not_poison_window_start_for_others(
    db_session: AsyncSession,
):
    """Regression test: a single event with a corrupted/ancient timestamp
    (clock skew, a replayed log line -- this exact scenario shipped in
    generate_demo_log.py's own "malformed sample" data, which parsed
    successfully with a hardcoded year-old timestamp) must not make
    window_start = min(event timestamps) collapse to that ancient value for
    the *whole* flush. If it did, every "seen before window_start" check in
    this file would treat every client as brand new, forever."""
    await alert_settings_service.update_settings(
        db_session, [DomainCategoryLabel.GAMBLING], non_work_minutes_threshold=120, client_daily_byte_quota_bytes=None
    )
    db_session.add(
        RawEvent(
            timestamp=WINDOW_START - timedelta(hours=2),
            duration_ms=1,
            client_ip="10.0.0.24",
            action="TCP_MISS",
            status_code=200,
            bytes=100,
            method="GET",
            url="http://gambling-paradise.bet/",
            domain="gambling-paradise.bet",
            user=None,
            hierarchy=None,
            peer=None,
            content_type=None,
            blocked=False,
        )
    )
    await db_session.commit()

    events = [
        _event(client_ip="10.0.0.24", domain="gambling-paradise.bet", blocked=False),
        # One corrupted event in the same batch, over a year in the past.
        _event(
            client_ip="10.0.0.99",
            domain="unrelated.example",
            blocked=False,
            timestamp=WINDOW_START.replace(year=WINDOW_START.year - 1),
        ),
    ]
    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited" and a.client_ip == "10.0.0.24"]
