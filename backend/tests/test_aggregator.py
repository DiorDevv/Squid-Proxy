"""Exercises Aggregator.flush() end-to-end against a real (temp) DB session,
rather than hand-inserting aggregate rows -- this is the path that a prior
bug slipped through (a freshly-constructed row's counters are None until
SQLAlchemy flushes it, so `row.total_requests += n` raised TypeError on the
very first event in every bucket)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.insights.base import Anomaly, AnomalySeverity, Insight, InsightsProvider
from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
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


async def test_flush_chunks_a_large_raw_events_insert_without_dropping_or_duplicating_rows(
    db_engine, monkeypatch
):
    """A single flush window with enough events to exceed one INSERT
    statement's safe parameter budget must still persist every raw_events
    row exactly once, split across multiple statements inside the same
    transaction -- mirrors bulk_upsert_sum's own chunking test
    (test_db_upsert.py), for the plain raw_events insert this module does
    separately. Reproduced against a real ~750k-event ring-buffer-overflow
    burst: one un-chunked INSERT of that size took 91s as a single
    statement (see db_upsert.chunk_rows' docstring)."""
    from app.services import db_upsert

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    # RawEvent's insert dict has 15 columns -- enough rows to force several
    # chunks at the module's configured _MAX_VARIABLES_PER_STATEMENT / 15
    # chunk size.
    row_count = 4 * (db_upsert._MAX_VARIABLES_PER_STATEMENT // 15)
    ring_buffer = RingBuffer(max_events=row_count + 10)
    for i in range(row_count):
        ring_buffer.append(parse_line(squid_line(f"domain-{i}.example", client_ip=f"10.0.{i // 256}.{i % 256}")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    result = await aggregator.flush()

    assert result.events_flushed == row_count

    async with session_factory() as session:
        raw_rows = (await session.execute(select(RawEvent))).scalars().all()
        assert len(raw_rows) == row_count
        domains = {row.domain for row in raw_rows}
        assert domains == {f"domain-{i}.example" for i in range(row_count)}


async def test_flush_buckets_requests_by_client_and_category(db_engine, monkeypatch):
    """youtube.com is a known hostname (see category_inference.py) that
    auto-infers to VIDEO_STREAMING with no admin override needed -- this
    covers the per-event categorization added to flush() to populate
    client_category_minute_aggregates (see category_usage_monitor.py, which
    reads this table instead of re-scanning raw_events per client)."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("youtube.com", client_ip="10.0.0.5")))
    ring_buffer.append(parse_line(squid_line("youtube.com", client_ip="10.0.0.5")))
    ring_buffer.append(parse_line(squid_line("youtube.com", client_ip="10.0.0.6")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    await aggregator.flush()

    async with session_factory() as session:
        rows = (await session.execute(select(ClientCategoryMinuteAggregate))).scalars().all()
        by_client = {row.client_ip: row for row in rows}

        assert by_client["10.0.0.5"].category == DomainCategoryLabel.VIDEO_STREAMING
        assert by_client["10.0.0.5"].request_count == 2
        assert by_client["10.0.0.5"].total_bytes == 2048
        assert by_client["10.0.0.6"].request_count == 1


async def test_flush_keeps_two_branches_hitting_the_same_domain_in_the_same_minute_separate(
    db_engine, monkeypatch
):
    """Same domain, same client_ip, same minute bucket, but two different
    branches -- the aggregator must not merge them into one row (that would
    silently mix two different sites' traffic together)."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com"), branch="hq"))
    ring_buffer.append(parse_line(squid_line("example.com"), branch="hq"))
    ring_buffer.append(parse_line(squid_line("example.com"), branch="branch-office"))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    result = await aggregator.flush()
    assert result.events_flushed == 3

    async with session_factory() as session:
        minute_rows = {row.branch: row for row in (await session.execute(select(MinuteAggregate))).scalars()}
        assert minute_rows["hq"].total_requests == 2
        assert minute_rows["branch-office"].total_requests == 1

        domain_rows = (await session.execute(select(DomainMinuteAggregate))).scalars().all()
        assert len(domain_rows) == 2
        by_branch = {row.branch: row for row in domain_rows}
        assert by_branch["hq"].request_count == 2
        assert by_branch["branch-office"].request_count == 1

        client_rows = (await session.execute(select(ClientMinuteAggregate))).scalars().all()
        assert len(client_rows) == 2

        raw_branches = sorted(
            row.branch for row in (await session.execute(select(RawEvent))).scalars().all()
        )
        assert raw_branches == ["branch-office", "hq", "hq"]


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


async def test_flush_does_not_advance_past_events_lost_to_a_failed_commit(db_engine, monkeypatch):
    """If the DB transaction fails (a transient hiccup, a constraint
    violation), flush() must not have already marked those events as
    flushed -- otherwise they're silently skipped forever on the next
    attempt, never having actually been persisted."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    ring_buffer.append(parse_line(squid_line("example.com")))

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    original_commit = AsyncSession.commit
    call_count = 0

    async def flaky_commit(self):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated transient DB failure")
        return await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)

    with pytest.raises(RuntimeError):
        await aggregator.flush()

    # Still considered unflushed -- not silently skipped.
    assert aggregator.backlog_size == 1

    # A retry (the "transient" failure is over now) must actually persist
    # it, not no-op because it thinks this event was already handled.
    result = await aggregator.flush()
    assert result.events_flushed == 1
    assert aggregator.backlog_size == 0

    async with session_factory() as session:
        minute_row = (await session.execute(select(MinuteAggregate))).scalar_one()
        assert minute_row.total_requests == 1


async def test_flush_with_no_new_events_is_a_noop(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=100)
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)
    result = await aggregator.flush()

    assert result.events_flushed == 0


async def test_flush_calls_on_flush_committed_only_after_a_successful_commit(db_engine, monkeypatch):
    """on_flush_committed is how a LogTailer knows it's finally safe to
    persist its read position to disk (see log_tailer.py's checkpoint()) --
    it must fire once real events are durably committed, and never fire for
    a no-op flush (nothing was committed, so there's nothing new to
    checkpoint)."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    calls = []
    ring_buffer = RingBuffer(max_events=100)
    aggregator = Aggregator(
        ring_buffer=ring_buffer, interval_seconds=60, on_flush_committed=lambda: calls.append(True)
    )

    await aggregator.flush()
    assert calls == []  # no events -- nothing committed, callback must not fire

    ring_buffer.append(parse_line(squid_line("example.com")))
    await aggregator.flush()
    assert len(calls) == 1


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


def test_backlog_size_and_ratio_reflect_unflushed_events():
    ring_buffer = RingBuffer(max_events=10)
    for _ in range(4):
        ring_buffer.append(parse_line(squid_line("example.com")))
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    assert aggregator.backlog_size == 4
    assert aggregator.backlog_ratio == 0.4
    assert aggregator.events_likely_lost is False


async def test_flush_resets_backlog_to_zero(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring_buffer = RingBuffer(max_events=10)
    ring_buffer.append(parse_line(squid_line("example.com")))
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    assert aggregator.backlog_size == 1
    await aggregator.flush()
    assert aggregator.backlog_size == 0


def test_events_likely_lost_once_ring_buffer_evicts_past_last_flush():
    """A ring buffer with a small maxlen simulates falling far enough
    behind that eviction destroys events the aggregator never flushed --
    events_since() can't see this on its own (it only returns whatever's
    still physically present), which is exactly why this needs its own
    check based on id arithmetic instead."""
    ring_buffer = RingBuffer(max_events=3)
    for _ in range(8):
        ring_buffer.append(parse_line(squid_line("example.com")))
    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    assert len(ring_buffer) == 3
    assert aggregator.backlog_size == 8
    assert aggregator.events_likely_lost is True
