"""Unit tests for StatisticalAnomalyProvider, run directly against the
in-memory test DB (db_session fixture) so historical-baseline queries hit a
real table rather than a mock."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.anomaly import StatisticalAnomalyProvider
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
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
        branch="default",
    )


async def _seed_prior_anomaly(
    session: AsyncSession,
    kind: str,
    *,
    age: timedelta,
    branch: str = "default",
    client_ip: str | None = None,
    domain: str | None = None,
) -> None:
    session.add(
        AnomalyEvent(
            generated_at=WINDOW_START - age,
            title=kind,
            description=kind,
            severity=AnomalySeverity.HIGH,
            client_ip=client_ip,
            domain=domain,
            branch=branch,
            kind=kind,
            params={},
        )
    )
    await session.commit()


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
    assert spikes[0].kind == "traffic_spike"
    assert spikes[0].params == {"current": 40, "baseline": 10, "windows": 6}


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


async def test_traffic_spike_not_flagged_below_absolute_minimum(db_session: AsyncSession):
    """A quiet branch (baseline ~2/window) seeing 20 requests is 10x its
    median, but 20 requests is still nothing -- the absolute floor keeps it
    from being alerted on."""
    await _seed_minute_history(db_session, count=6, total_requests=2)
    events = [_event() for _ in range(20)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_traffic_spike_baseline_uses_median_so_a_prior_spike_does_not_mask(
    db_session: AsyncSession,
):
    """History is five calm windows plus one earlier 800-request spike. The
    mean of that is ~140 (so mean*3 would hide today's jump); the median is
    10, so a 45-request window is correctly flagged."""
    for i, total in enumerate([10, 10, 10, 10, 10, 800]):
        db_session.add(
            MinuteAggregate(
                bucket_ts=WINDOW_START - timedelta(minutes=i + 1),
                total_requests=total,
                blocked_requests=0,
                allowed_requests=total,
                total_bytes=0,
            )
        )
    await db_session.commit()
    events = [_event() for _ in range(45)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    spikes = [a for a in anomalies if a.title == "Traffic spike detected"]
    assert len(spikes) == 1
    assert spikes[0].params == {"current": 45, "baseline": 10, "windows": 6}


async def test_traffic_spike_tolerates_a_normally_noisy_stream(db_session: AsyncSession):
    """A stream that alternates 10 and 50 per window has a wide normal band
    (median 30, MAD 20 -> threshold 130). A 100-request window is inside
    that band and must not be flagged."""
    for i, total in enumerate([10, 50] * 5):
        db_session.add(
            MinuteAggregate(
                bucket_ts=WINDOW_START - timedelta(minutes=i + 1),
                total_requests=total,
                blocked_requests=0,
                allowed_requests=total,
                total_bytes=0,
            )
        )
    await db_session.commit()
    events = [_event() for _ in range(100)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_traffic_spike_not_reflagged_within_cooldown(db_session: AsyncSession):
    await _seed_minute_history(db_session, count=6, total_requests=10)
    await _seed_prior_anomaly(db_session, "traffic_spike", age=timedelta(minutes=20))
    events = [_event() for _ in range(40)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_traffic_spike_reflagged_after_cooldown_elapses(db_session: AsyncSession):
    await _seed_minute_history(db_session, count=6, total_requests=10)
    await _seed_prior_anomaly(db_session, "traffic_spike", age=timedelta(hours=2))
    events = [_event() for _ in range(40)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert [a for a in anomalies if a.title == "Traffic spike detected"]


async def test_client_blocked_ratio_cooldown_is_per_client(db_session: AsyncSession):
    await _seed_prior_anomaly(
        db_session, "client_blocked_ratio", age=timedelta(minutes=10), client_ip="10.0.0.9"
    )
    events = (
        [_event(client_ip="10.0.0.9", blocked=True) for _ in range(4)]
        + [_event(client_ip="10.0.0.9", blocked=False)]
        + [_event(client_ip="10.0.0.10", blocked=True) for _ in range(4)]
        + [_event(client_ip="10.0.0.10", blocked=False)]
    )

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    flagged = {a.client_ip for a in anomalies if a.title == "Client mostly blocked"}
    assert flagged == {"10.0.0.10"}


async def test_new_blocked_domain_not_reflagged_within_cooldown(db_session: AsyncSession):
    await _seed_prior_anomaly(
        db_session, "new_blocked_domain", age=timedelta(minutes=5), domain="evil.example"
    )
    events = [_event(domain="evil.example", blocked=True)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "New blocked domain observed"]


async def test_new_blocked_domain_is_flagged(db_session: AsyncSession):
    events = [_event(domain="evil.example", blocked=True)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    new_domain_anomalies = [a for a in anomalies if a.title == "New blocked domain observed"]
    assert len(new_domain_anomalies) == 1
    assert new_domain_anomalies[0].domain == "evil.example"
    assert new_domain_anomalies[0].kind == "new_blocked_domain"
    assert new_domain_anomalies[0].params == {"domain": "evil.example"}


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
    assert client_anomalies[0].kind == "client_blocked_ratio"
    assert client_anomalies[0].params == {"clientIp": "10.0.0.9", "blocked": 4, "total": 5, "ratio": 80}


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
        db_session,
        [DomainCategoryLabel.GAMBLING],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
    )
    events = [_event(client_ip="10.0.0.20", domain="gambling-paradise.bet", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    flagged = [a for a in anomalies if a.title == "Sensitive category visited"]
    assert len(flagged) == 1
    assert flagged[0].client_ip == "10.0.0.20"
    assert flagged[0].domain == "gambling-paradise.bet"
    assert flagged[0].kind == "sensitive_category_visit"
    assert flagged[0].params == {
        "clientIp": "10.0.0.20",
        "domain": "gambling-paradise.bet",
        "category": "gambling",
    }


async def test_sensitive_category_visit_not_flagged_when_no_categories_configured(db_session: AsyncSession):
    # No alert_settings row at all -- default is "nothing configured".
    events = [_event(client_ip="10.0.0.21", domain="gambling-paradise.bet", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited"]


async def test_sensitive_category_visit_not_flagged_for_uninvolved_category(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session,
        [DomainCategoryLabel.GAMBLING],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
    )
    events = [_event(client_ip="10.0.0.22", domain="github.com", blocked=False)]

    anomalies = await StatisticalAnomalyProvider().detect_anomalies(events, db_session)

    assert not [a for a in anomalies if a.title == "Sensitive category visited"]


async def test_sensitive_category_repeat_visit_is_not_flagged(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session,
        [DomainCategoryLabel.GAMBLING],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
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
        db_session,
        [DomainCategoryLabel.GAMBLING],
        non_work_minutes_threshold=120,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
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

    assert not [
        a for a in anomalies if a.title == "Sensitive category visited" and a.client_ip == "10.0.0.24"
    ]
