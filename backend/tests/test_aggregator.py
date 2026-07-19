"""Exercises Aggregator.flush() end-to-end against a real (temp) DB session,
rather than hand-inserting aggregate rows -- this is the path that a prior
bug slipped through (a freshly-constructed row's counters are None until
SQLAlchemy flushes it, so `row.total_requests += n` raised TypeError on the
very first event in every bucket)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.insights.base import Anomaly, AnomalySeverity, Insight, InsightsProvider
from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services.aggregator import Aggregator
from app.services.event_store import RingBuffer
from app.services.log_parser import ParsedEvent, parse_line


def squid_line(domain: str, client_ip: str = "10.0.0.5", blocked: bool = False) -> str:
    action_status = "TCP_DENIED/403" if blocked else "TCP_MISS/200"
    return (
        f"1737100800.123 45 {client_ip} {action_status} 1024 GET "
        f"http://{domain}/ alice HIER_DIRECT/93.184.216.34 text/html"
    )


async def test_flush_writes_minute_domain_and_client_aggregates(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com")))
    ring_buffer.append(parse_line(squid_line("example.com")))
    ring_buffer.append(parse_line(squid_line("blocked.com", blocked=True)))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    result = await aggregator.flush()

    assert result.events_flushed == 3

    async with session_factory() as session:
        minute_row = (await session.execute(select(MinuteAggregate))).scalar_one()
        assert minute_row.total_requests == 3
        assert minute_row.blocked_requests == 1
        assert minute_row.allowed_requests == 2

        domain_rows = {row.domain: row for row in (await session.execute(select(DomainMinuteAggregate))).scalars()}
        assert domain_rows["example.com"].request_count == 2
        assert domain_rows["example.com"].total_bytes == 2048
        assert domain_rows["blocked.com"].blocked_count == 1

        client_row = (await session.execute(select(ClientMinuteAggregate))).scalar_one()
        assert client_row.request_count == 3

        raw_count = len((await session.execute(select(RawEvent))).scalars().all())
        assert raw_count == 3


async def test_flush_on_second_call_increments_existing_rows_rather_than_duplicating(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    await aggregator.flush()

    ring_buffer.append(parse_line(squid_line("example.com")))
    await aggregator.flush()

    async with session_factory() as session:
        rows = (await session.execute(select(MinuteAggregate))).scalars().all()
        assert len(rows) == 1
        assert rows[0].total_requests == 2


async def test_flush_with_no_new_events_is_a_noop(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    result = await aggregator.flush()

    assert result.events_flushed == 0


class _StubAnomalyProvider(InsightsProvider):
    """Always reports one canned anomaly, regardless of the window --
    isolates the flush -> persist -> alert wiring from real detection logic
    (that's covered separately in test_insights_anomaly.py)."""

    async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
        return []

    async def detect_anomalies(self, events: list[ParsedEvent], session) -> list[Anomaly]:
        return [
            Anomaly(
                title="Traffic spike detected",
                description="stub anomaly for wiring test",
                severity=AnomalySeverity.HIGH,
                generated_at=datetime.now(UTC),
            )
        ]


async def test_flush_persists_and_alerts_on_detected_anomalies(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(aggregator_module, "get_insights_provider", lambda: _StubAnomalyProvider())

    alerted: list[AnomalyEvent] = []

    async def _fake_maybe_alert(event: AnomalyEvent) -> None:
        alerted.append(event)

    monkeypatch.setattr(aggregator_module, "maybe_alert", _fake_maybe_alert)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    await aggregator.flush()

    async with session_factory() as session:
        rows = (await session.execute(select(AnomalyEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].title == "Traffic spike detected"

    assert len(alerted) == 1
    assert alerted[0].title == "Traffic spike detected"


async def test_flush_insights_failure_does_not_break_the_flush(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    class _BrokenProvider(InsightsProvider):
        async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
            return []

        async def detect_anomalies(self, events: list[ParsedEvent], session) -> list[Anomaly]:
            raise RuntimeError("boom")

    monkeypatch.setattr(aggregator_module, "get_insights_provider", lambda: _BrokenProvider())

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    # Must not raise even though the provider does.
    result = await aggregator.flush()
    assert result.events_flushed == 1
