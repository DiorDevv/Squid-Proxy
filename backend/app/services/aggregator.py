"""Periodically flushes newly-arrived ring buffer events into durable storage.

Every AGGREGATION_INTERVAL_SECONDS (default 60s):
  - per-minute global totals -> minute_aggregates
  - per-minute per-domain counts -> domain_minute_aggregates
  - per-minute per-client counts -> client_minute_aggregates
  - full per-event detail -> raw_events (shorter retention, see retention.py)
  - anomaly detection over the same window, once the above has landed (see
    app/insights/base.py) -- persisted anomalies get a best-effort alert
    (app/services/alerting.py)
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, insert, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights import get_insights_provider
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import insights_service
from app.services.alerting import maybe_alert
from app.services.category_inference import effective_category
from app.services.db_upsert import bulk_upsert_sum
from app.services.domain_category_service import get_overrides_map
from app.services.event_store import RingBuffer, StoredEvent

logger = logging.getLogger(__name__)


@dataclass
class _MinuteTotals:
    total: int = 0
    blocked: int = 0
    allowed: int = 0
    bytes_: int = 0


@dataclass
class _DomainTotals:
    count: int = 0
    blocked: int = 0
    bytes_: int = 0


@dataclass
class _ClientTotals:
    count: int = 0
    blocked: int = 0
    bytes_: int = 0


@dataclass
class _CategoryTotals:
    count: int = 0
    bytes_: int = 0


@dataclass
class FlushResult:
    events_flushed: int = 0
    buckets_touched: set[tuple[datetime, str]] = field(default_factory=set)


class Aggregator:
    # If the unflushed backlog reaches this fraction of the ring buffer's
    # capacity, eviction (deque(maxlen=...) silently dropping the oldest
    # entries) is close enough to start losing events that it's worth
    # warning about before that actually happens.
    BACKLOG_WARNING_RATIO = 0.8

    def __init__(self, ring_buffer: RingBuffer, interval_seconds: int = 60) -> None:
        self.ring_buffer = ring_buffer
        self.interval_seconds = interval_seconds
        self._last_flushed_id = 0
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def backlog_size(self) -> int:
        """How many events are waiting on the next flush, by id arithmetic
        -- cheap (no list materialization), unlike counting
        events_since()'s result."""
        return max(0, self.ring_buffer.latest_id - self._last_flushed_id)

    @property
    def backlog_ratio(self) -> float:
        max_events = self.ring_buffer.max_events
        return 0.0 if max_events <= 0 else self.backlog_size / max_events

    @property
    def events_likely_lost(self) -> bool:
        """True once the ring buffer's maxlen eviction has already
        destroyed events between the aggregator's last flush point and what
        it's currently holding. events_since() alone can't detect this --
        it just returns whatever's still physically in the deque -- so this
        compares the *expected* backlog (by id arithmetic) against what's
        actually still present."""
        return self.backlog_size > len(self.ring_buffer)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever(), name="aggregator")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()

    async def _run_forever(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except TimeoutError:
                await self._flush_catching_errors()
        await self._flush_catching_errors()

    async def _flush_catching_errors(self) -> None:
        """A single bad flush (a query bug, a transient DB hiccup) must never
        permanently stop periodic aggregation -- matches the log tailer's
        "never crashes the process" resilience (see log_tailer.py)."""
        try:
            await self.flush()
        except Exception:
            logger.exception("Aggregator flush failed; will retry next interval")

    @staticmethod
    def _bucket(ts: datetime) -> datetime:
        return ts.replace(second=0, microsecond=0)

    async def flush(self) -> FlushResult:
        if self.events_likely_lost:
            logger.error(
                "Ring buffer overflowed before the aggregator could flush -- "
                "some events were dropped without ever being persisted. "
                "Raise RING_BUFFER_MAX_EVENTS or reduce AGGREGATION_INTERVAL_SECONDS.",
                extra={"backlog_size": self.backlog_size, "buffered": len(self.ring_buffer)},
            )
        elif self.backlog_ratio >= self.BACKLOG_WARNING_RATIO:
            logger.warning(
                "Aggregator is falling behind: unflushed backlog is "
                "approaching the ring buffer's capacity",
                extra={
                    "backlog_size": self.backlog_size,
                    "backlog_ratio": round(self.backlog_ratio, 2),
                },
            )

        events = self.ring_buffer.events_since(self._last_flushed_id)
        if not events:
            return FlushResult()

        async with AsyncSessionLocal() as session:
            # Loaded once per flush, not once per event -- every event in
            # this window shares the same admin-override snapshot.
            overrides = await get_overrides_map(session)

            # Building the buckets is pure CPU work (dict bookkeeping +
            # effective_category()'s lru_cache'd lookup, no I/O) -- run via
            # asyncio.to_thread so a large backlog (e.g. rsyslog draining a
            # disk queue after a branch/central link outage, same scenario
            # log_tailer.py's module docstring describes) doesn't stall the
            # event loop for the ~400ms/150k-events this loop measured at.
            minute_buckets, domain_buckets, client_buckets, category_buckets, raw_rows = (
                await asyncio.to_thread(self._build_buckets, events, overrides)
            )

            await self._bulk_upsert_minute(session, minute_buckets)
            await self._bulk_upsert_domain(session, domain_buckets)
            await self._bulk_upsert_client(session, client_buckets)
            await self._bulk_upsert_category(session, category_buckets)
            # Core bulk insert (plain dicts), not session.add_all() with ORM
            # objects -- for a large backlog, add_all()'s identity-map/
            # unit-of-work bookkeeping is itself a real synchronous CPU cost
            # (measured at ~960ms for 150k rows, on top of however long the
            # implicit flush inside commit() then also takes), all of it on
            # the event loop thread since session operations must stay
            # there. The Core insert measured ~15% faster overall and, more
            # importantly, yielded control back to the event loop far more
            # often while running (heartbeat ticks landed during ~87% of
            # its duration vs. ~58% for add_all()+commit()).
            if raw_rows:
                await session.execute(insert(RawEvent.__table__), raw_rows)
            await session.commit()

        # Only advance past these events once they're durably committed --
        # doing this any earlier (e.g. right after events_since()) would
        # mean a failed commit (a transient DB hiccup, a bug) still marks
        # them as flushed, silently skipping them forever on the next
        # attempt despite nothing having actually been persisted.
        self._last_flushed_id = events[-1].id

        logger.info(
            "Aggregator flush complete",
            extra={"events_flushed": len(events), "minute_buckets": len(minute_buckets)},
        )
        await self._run_insights(events)
        return FlushResult(events_flushed=len(events), buckets_touched=set(minute_buckets))

    def _build_buckets(
        self, events: list[StoredEvent], overrides: dict[str, DomainCategoryLabel]
    ) -> tuple[
        dict[tuple[datetime, str], _MinuteTotals],
        dict[tuple[datetime, str, str], _DomainTotals],
        dict[tuple[datetime, str, str, str | None], _ClientTotals],
        dict[tuple[datetime, str, str, DomainCategoryLabel], _CategoryTotals],
        list[dict],
    ]:
        """Runs inside a worker thread (see flush()) -- pure in-memory
        bookkeeping over an already-fetched event batch, no I/O, no asyncio
        state touched."""
        minute_buckets: dict[tuple[datetime, str], _MinuteTotals] = defaultdict(_MinuteTotals)
        domain_buckets: dict[tuple[datetime, str, str], _DomainTotals] = defaultdict(_DomainTotals)
        client_buckets: dict[tuple[datetime, str, str, str | None], _ClientTotals] = defaultdict(
            _ClientTotals
        )
        category_buckets: dict[
            tuple[datetime, str, str, DomainCategoryLabel], _CategoryTotals
        ] = defaultdict(_CategoryTotals)
        raw_rows: list[dict] = []

        for stored in events:
            ev = stored.event
            bucket = self._bucket(ev.timestamp)

            mb = minute_buckets[(bucket, ev.branch)]
            mb.total += 1
            mb.bytes_ += ev.bytes
            if ev.blocked:
                mb.blocked += 1
            else:
                mb.allowed += 1

            if ev.domain:
                db = domain_buckets[(bucket, ev.domain, ev.branch)]
                db.count += 1
                db.bytes_ += ev.bytes
                if ev.blocked:
                    db.blocked += 1

                category = effective_category(ev.domain, overrides)
                ctb = category_buckets[(bucket, ev.client_ip, ev.branch, category)]
                ctb.count += 1
                ctb.bytes_ += ev.bytes

            cb = client_buckets[(bucket, ev.client_ip, ev.branch, ev.user)]
            cb.count += 1
            cb.bytes_ += ev.bytes
            if ev.blocked:
                cb.blocked += 1

            raw_rows.append(
                {
                    "timestamp": ev.timestamp,
                    "duration_ms": ev.duration_ms,
                    "client_ip": ev.client_ip,
                    "branch": ev.branch,
                    "action": ev.action,
                    "status_code": ev.status_code,
                    "bytes": ev.bytes,
                    "method": ev.method,
                    "url": ev.url,
                    "domain": ev.domain,
                    "user": ev.user,
                    "hierarchy": ev.hierarchy,
                    "peer": ev.peer,
                    "content_type": ev.content_type,
                    "blocked": ev.blocked,
                }
            )

        return minute_buckets, domain_buckets, client_buckets, category_buckets, raw_rows

    async def _run_insights(self, events: list[StoredEvent]) -> None:
        """Anomaly detection over the window just flushed. Best-effort: a
        broken/misbehaving provider must never take down the flush loop."""
        provider = get_insights_provider()
        parsed_events = [stored.event for stored in events]

        async with AsyncSessionLocal() as session:
            try:
                anomalies = await provider.detect_anomalies(parsed_events, session)
            except Exception:
                logger.exception("Insights provider failed; skipping this window")
                return
            if not anomalies:
                return

            rows = insights_service.persist(session, anomalies)
            await session.commit()

        for row in rows:
            await maybe_alert(row)

    async def _bulk_upsert_minute(
        self, session: AsyncSession, minute_buckets: dict[tuple[datetime, str], _MinuteTotals]
    ) -> None:
        if not minute_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "branch": branch,
                "total_requests": totals.total,
                "blocked_requests": totals.blocked,
                "allowed_requests": totals.allowed,
                "total_bytes": totals.bytes_,
            }
            for (bucket, branch), totals in minute_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            MinuteAggregate.__table__,
            rows,
            index_elements=[MinuteAggregate.bucket_ts, MinuteAggregate.branch],
            sum_columns=["total_requests", "blocked_requests", "allowed_requests", "total_bytes"],
        )

    async def _bulk_upsert_domain(
        self,
        session: AsyncSession,
        domain_buckets: dict[tuple[datetime, str, str], _DomainTotals],
    ) -> None:
        if not domain_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "domain": domain,
                "branch": branch,
                "request_count": totals.count,
                "blocked_count": totals.blocked,
                "total_bytes": totals.bytes_,
            }
            for (bucket, domain, branch), totals in domain_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            DomainMinuteAggregate.__table__,
            rows,
            index_elements=[
                DomainMinuteAggregate.bucket_ts,
                DomainMinuteAggregate.domain,
                DomainMinuteAggregate.branch,
            ],
            sum_columns=["request_count", "blocked_count", "total_bytes"],
        )

    async def _bulk_upsert_category(
        self,
        session: AsyncSession,
        category_buckets: dict[
            tuple[datetime, str, str, DomainCategoryLabel], _CategoryTotals
        ],
    ) -> None:
        if not category_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "client_ip": client_ip,
                "branch": branch,
                "category": category,
                "request_count": totals.count,
                "total_bytes": totals.bytes_,
            }
            for (bucket, client_ip, branch, category), totals in category_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            ClientCategoryMinuteAggregate.__table__,
            rows,
            index_elements=[
                ClientCategoryMinuteAggregate.bucket_ts,
                ClientCategoryMinuteAggregate.client_ip,
                ClientCategoryMinuteAggregate.category,
                ClientCategoryMinuteAggregate.branch,
            ],
            sum_columns=["request_count", "total_bytes"],
        )

    async def _bulk_upsert_client(
        self,
        session: AsyncSession,
        client_buckets: dict[tuple[datetime, str, str, str | None], _ClientTotals],
    ) -> None:
        if not client_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "client_ip": client_ip,
                "branch": branch,
                "user": user,
                "request_count": totals.count,
                "blocked_count": totals.blocked,
                "total_bytes": totals.bytes_,
            }
            for (bucket, client_ip, branch, user), totals in client_buckets.items()
        ]
        # The unique index on this table is (bucket_ts, client_ip, branch,
        # coalesce(user, '')) -- see migration 466aaa85c9f3's docstring for
        # why: `user` is nullable, and plain SQL treats NULL as distinct
        # from itself, so the conflict target has to match that expression
        # exactly rather than the plain (bucket_ts, client_ip, branch, user)
        # columns. The '' has to be a literal, not a bound parameter --
        # SQLite only recognizes an ON CONFLICT expression as matching an
        # expression index when its constant subexpressions are literals too.
        await bulk_upsert_sum(
            session,
            ClientMinuteAggregate.__table__,
            rows,
            index_elements=[
                ClientMinuteAggregate.bucket_ts,
                ClientMinuteAggregate.client_ip,
                ClientMinuteAggregate.branch,
                func.coalesce(ClientMinuteAggregate.user, literal_column("''")),
            ],
            sum_columns=["request_count", "blocked_count", "total_bytes"],
        )
