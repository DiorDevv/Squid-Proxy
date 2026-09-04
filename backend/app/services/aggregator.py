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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, insert, literal_column
from sqlalchemy.exc import DataError
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights import get_insights_provider
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.ops_aggregate import (
    HierarchyMinuteAggregate,
    HttpMinuteAggregate,
    ResultCodeMinuteAggregate,
    UserCategoryMinuteAggregate,
)
from app.models.raw_event import RawEvent
from app.services import insights_service
from app.services.alerting import maybe_alert
from app.services.category_inference import effective_category
from app.services.db_upsert import bulk_upsert_sum, chunk_rows, declared_table, max_variables_for
from app.services.domain_category_service import get_overrides_map
from app.services.event_store import RingBuffer, StoredEvent

logger = logging.getLogger(__name__)


@dataclass
class _MinuteTotals:
    total: int = 0
    blocked: int = 0
    allowed: int = 0
    bytes_: int = 0
    hit: int = 0
    miss: int = 0
    # Response-time histogram (see MinuteAggregate's perf columns) -- six
    # disjoint bands plus the raw sum, enough for an approximate
    # p50/p95/p99 and an exact mean.
    dur_sum: int = 0
    dur_lt_100: int = 0
    dur_lt_300: int = 0
    dur_lt_1000: int = 0
    dur_lt_3000: int = 0
    dur_lt_10000: int = 0
    dur_gte_10000: int = 0


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
class _CountBytes:
    """Shared shape for the four Squid-operational per-minute buckets
    (result code, HTTP method/status, hierarchy, per-user category) -- all
    only ever need a request count and a byte total."""

    count: int = 0
    bytes_: int = 0


def _hierarchy_code(raw: str | None) -> str:
    """The code prefix of Squid's hierarchy field ("HIER_DIRECT/1.2.3.4" ->
    "HIER_DIRECT"); "-" / empty -> "NONE"."""
    if not raw or raw == "-":
        return "NONE"
    return raw.split("/", 1)[0].strip() or "NONE"


def _add_duration(totals: _MinuteTotals, duration_ms: int | None) -> None:
    if duration_ms is None or duration_ms < 0:
        return
    totals.dur_sum += duration_ms
    if duration_ms < 100:
        totals.dur_lt_100 += 1
    elif duration_ms < 300:
        totals.dur_lt_300 += 1
    elif duration_ms < 1000:
        totals.dur_lt_1000 += 1
    elif duration_ms < 3000:
        totals.dur_lt_3000 += 1
    elif duration_ms < 10000:
        totals.dur_lt_10000 += 1
    else:
        totals.dur_gte_10000 += 1


@dataclass
class FlushResult:
    events_flushed: int = 0
    buckets_touched: set[tuple[datetime, str]] = field(default_factory=set)


def _is_cache_hit(action: str) -> bool:
    """Squid's %Ss result tag (RawEvent.action) -- "HIT" appears in every
    tag meaning the response was served from cache without going to the
    origin/peer (TCP_HIT, TCP_MEM_HIT, TCP_IMS_HIT, TCP_CF_HIT, ...). This
    substring check is the same convention Squid's own log analyzers
    (sarg, calamaris) use, rather than an exhaustive tag list that would
    silently miss a variant this project's author hadn't seen yet.

    TCP_REFRESH_UNMODIFIED is checked explicitly since it has neither
    substring: a revalidation (conditional GET) confirmed the cached copy
    was still fresh, so it's a hit despite the round-trip to the origin."""
    action = action.upper()
    return "HIT" in action or "REFRESH_UNMODIFIED" in action


def _is_cache_miss(action: str) -> bool:
    """The complement of _is_cache_hit for tags where the cache *could* have
    helped but didn't (TCP_MISS, TCP_CLIENT_REFRESH_MISS, ...) -- deliberately
    excludes TCP_DENIED (blocked, never reached the cache layer) and
    TCP_TUNNEL (a CONNECT tunnel, cache doesn't apply) so
    stats_service.get_cache_efficiency's hit/(hit+miss) ratio reflects
    actual cacheable traffic, not every request regardless of type.

    TCP_REFRESH_MODIFIED is checked explicitly since it has neither "MISS"
    nor "HIT" as a substring: a revalidation found the cached copy stale, so
    the full response had to be re-fetched -- a miss despite the "REFRESH"
    tag looking cache-adjacent."""
    action = action.upper()
    return "MISS" in action or "REFRESH_MODIFIED" in action


class Aggregator:
    # If the unflushed backlog reaches this fraction of the ring buffer's
    # capacity, eviction (deque(maxlen=...) silently dropping the oldest
    # entries) is close enough to start losing events that it's worth
    # warning about before that actually happens.
    BACKLOG_WARNING_RATIO = 0.8

    def __init__(
        self,
        ring_buffer: RingBuffer,
        interval_seconds: int = 60,
        on_flush_committed: Callable[[], None] | None = None,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.interval_seconds = interval_seconds
        # Called synchronously right after a flush's commit() succeeds --
        # see LogTailer.checkpoint()/main.py's wiring. This is the only
        # point at which every event dispatched to on_event so far is
        # actually guaranteed durable, so it's the only safe moment for a
        # log tailer to persist how far it's read to disk (persisting
        # eagerly on every poll, the old behavior, could mark bytes as
        # "consumed" on disk before the events they produced ever reached
        # the database -- a crash in between silently lost them for good,
        # since a resumed tailer never re-reads bytes it already believes
        # it processed).
        self.on_flush_committed = on_flush_committed
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
            (
                minute_buckets,
                domain_buckets,
                client_buckets,
                category_buckets,
                code_buckets,
                http_buckets,
                hier_buckets,
                usercat_buckets,
                raw_rows,
            ) = await asyncio.to_thread(self._build_buckets, events, overrides)

            await self._bulk_upsert_minute(session, minute_buckets)
            await self._bulk_upsert_domain(session, domain_buckets)
            await self._bulk_upsert_client(session, client_buckets)
            await self._bulk_upsert_category(session, category_buckets)
            await self._bulk_upsert_result_code(session, code_buckets)
            await self._bulk_upsert_http(session, http_buckets)
            await self._bulk_upsert_hierarchy(session, hier_buckets)
            await self._bulk_upsert_user_category(session, usercat_buckets)
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
            #
            # Chunked via the same chunk_rows() the aggregate upserts below
            # use (see db_upsert.py), but with a dialect-aware, much larger
            # batch size (max_variables_for()) rather than that helper's own
            # SQLite-safe default -- raw_events gets one row per event with
            # no dedup, so a large backlog's row count dwarfs any aggregate
            # table's. Confirmed against a real ~750k-event burst (a ring
            # buffer overflow scenario, RING_BUFFER_MAX_EVENTS-sized): one
            # un-chunked INSERT took 91s as a single statement, but chunking
            # at the aggregate tables' own small batch size made it *worse*
            # (130s -- 12,500 round trips dominated). The larger
            # Postgres-specific batch size avoids both failure modes.
            for batch in chunk_rows(
                raw_rows,
                columns_per_row=len(raw_rows[0]) if raw_rows else 1,
                max_variables=max_variables_for(session),
            ):
                await self._insert_raw_events_batch(session, batch)
            await session.commit()

        # Only advance past these events once they're durably committed --
        # doing this any earlier (e.g. right after events_since()) would
        # mean a failed commit (a transient DB hiccup, a bug) still marks
        # them as flushed, silently skipping them forever on the next
        # attempt despite nothing having actually been persisted.
        self._last_flushed_id = events[-1].id
        if self.on_flush_committed is not None:
            self.on_flush_committed()

        logger.info(
            "Aggregator flush complete",
            extra={"events_flushed": len(events), "minute_buckets": len(minute_buckets)},
        )
        await self._run_insights(events)
        return FlushResult(events_flushed=len(events), buckets_touched=set(minute_buckets))

    async def _insert_raw_events_batch(
        self, session: AsyncSession, batch: Sequence[Mapping[str, object]]
    ) -> None:
        """Insert one chunk of raw_events rows. A DataError here means one or
        more rows carry a value no amount of retrying will make fit the
        column (historically a pre-BIGINT `bytes` overflow -- see
        raw_event.py). Left to propagate it would abort the whole flush
        transaction, and since flush() never advances _last_flushed_id past
        an uncommitted window the aggregator would re-run the identical
        poisoned batch every interval forever, backlog climbing until the
        ring buffer overflows. So: try the batch in a savepoint, and if it
        fails on a DataError, re-run its rows one per savepoint, dropping
        only the individual rows that still fail (loudly) and keeping the
        rest. The aggregate upserts earlier in this transaction are
        untouched either way. Any other exception still propagates -- a
        transient DB fault must remain a retry, not a silent drop."""
        try:
            async with session.begin_nested():
                await session.execute(insert(declared_table(RawEvent)), batch)
            return
        except DataError:
            logger.exception(
                "raw_events batch insert hit a DataError -- retrying rows individually to "
                "isolate and drop the un-persistable one(s) instead of wedging every flush",
                extra={"batch_size": len(batch)},
            )

        dropped = 0
        for row in batch:
            try:
                async with session.begin_nested():
                    await session.execute(insert(declared_table(RawEvent)), [row])
            except DataError:
                dropped += 1
                logger.error(
                    "Dropping un-persistable raw_events row",
                    extra={
                        "timestamp": row.get("timestamp"),
                        "client_ip": row.get("client_ip"),
                        "branch": row.get("branch"),
                        "bytes": row.get("bytes"),
                        "duration_ms": row.get("duration_ms"),
                        "url": row.get("url"),
                    },
                )
        if dropped:
            logger.error(
                "raw_events rows dropped this flush -- detail lost for these events, "
                "aggregate counts still include them",
                extra={"dropped": dropped, "batch_size": len(batch)},
            )

    def _build_buckets(
        self, events: list[StoredEvent], overrides: dict[str, DomainCategoryLabel]
    ) -> tuple[
        dict[tuple[datetime, str], _MinuteTotals],
        dict[tuple[datetime, str, str], _DomainTotals],
        dict[tuple[datetime, str, str, str | None], _ClientTotals],
        dict[tuple[datetime, str, str, DomainCategoryLabel], _CategoryTotals],
        dict[tuple[datetime, str, str], _CountBytes],
        dict[tuple[datetime, str, str, int], _CountBytes],
        dict[tuple[datetime, str, str], _CountBytes],
        dict[tuple[datetime, str, str, DomainCategoryLabel], _CountBytes],
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
        # Squid-operational buckets (see app/models/ops_aggregate.py).
        code_buckets: dict[tuple[datetime, str, str], _CountBytes] = defaultdict(_CountBytes)
        http_buckets: dict[tuple[datetime, str, str, int], _CountBytes] = defaultdict(_CountBytes)
        hier_buckets: dict[tuple[datetime, str, str], _CountBytes] = defaultdict(_CountBytes)
        usercat_buckets: dict[
            tuple[datetime, str, str, DomainCategoryLabel], _CountBytes
        ] = defaultdict(_CountBytes)
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
            if _is_cache_hit(ev.action):
                mb.hit += 1
            elif _is_cache_miss(ev.action):
                mb.miss += 1
            _add_duration(mb, ev.duration_ms)

            rc = code_buckets[(bucket, ev.branch, ev.action or "NONE")]
            rc.count += 1
            rc.bytes_ += ev.bytes

            hb = http_buckets[(bucket, ev.branch, ev.method or "NONE", ev.status_code or 0)]
            hb.count += 1
            hb.bytes_ += ev.bytes

            hr = hier_buckets[(bucket, ev.branch, _hierarchy_code(ev.hierarchy))]
            hr.count += 1
            hr.bytes_ += ev.bytes

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

                ucb = usercat_buckets[(bucket, ev.branch, ev.user or "", category)]
                ucb.count += 1
                ucb.bytes_ += ev.bytes

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

        return (
            minute_buckets,
            domain_buckets,
            client_buckets,
            category_buckets,
            code_buckets,
            http_buckets,
            hier_buckets,
            usercat_buckets,
            raw_rows,
        )

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
                "hit_requests": totals.hit,
                "miss_requests": totals.miss,
                "duration_sum_ms": totals.dur_sum,
                "dur_lt_100": totals.dur_lt_100,
                "dur_lt_300": totals.dur_lt_300,
                "dur_lt_1000": totals.dur_lt_1000,
                "dur_lt_3000": totals.dur_lt_3000,
                "dur_lt_10000": totals.dur_lt_10000,
                "dur_gte_10000": totals.dur_gte_10000,
            }
            for (bucket, branch), totals in minute_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(MinuteAggregate),
            rows,
            index_elements=[MinuteAggregate.bucket_ts, MinuteAggregate.branch],
            sum_columns=[
                "total_requests",
                "blocked_requests",
                "allowed_requests",
                "total_bytes",
                "hit_requests",
                "miss_requests",
                "duration_sum_ms",
                "dur_lt_100",
                "dur_lt_300",
                "dur_lt_1000",
                "dur_lt_3000",
                "dur_lt_10000",
                "dur_gte_10000",
            ],
        )

    async def _bulk_upsert_result_code(
        self,
        session: AsyncSession,
        code_buckets: dict[tuple[datetime, str, str], _CountBytes],
    ) -> None:
        if not code_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "branch": branch,
                "action": action,
                "request_count": totals.count,
                "total_bytes": totals.bytes_,
            }
            for (bucket, branch, action), totals in code_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(ResultCodeMinuteAggregate),
            rows,
            index_elements=[
                ResultCodeMinuteAggregate.bucket_ts,
                ResultCodeMinuteAggregate.branch,
                ResultCodeMinuteAggregate.action,
            ],
            sum_columns=["request_count", "total_bytes"],
        )

    async def _bulk_upsert_http(
        self,
        session: AsyncSession,
        http_buckets: dict[tuple[datetime, str, str, int], _CountBytes],
    ) -> None:
        if not http_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "branch": branch,
                "method": method,
                "status_code": status_code,
                "request_count": totals.count,
                "total_bytes": totals.bytes_,
            }
            for (bucket, branch, method, status_code), totals in http_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(HttpMinuteAggregate),
            rows,
            index_elements=[
                HttpMinuteAggregate.bucket_ts,
                HttpMinuteAggregate.branch,
                HttpMinuteAggregate.method,
                HttpMinuteAggregate.status_code,
            ],
            sum_columns=["request_count", "total_bytes"],
        )

    async def _bulk_upsert_hierarchy(
        self,
        session: AsyncSession,
        hier_buckets: dict[tuple[datetime, str, str], _CountBytes],
    ) -> None:
        if not hier_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "branch": branch,
                "hierarchy_code": code,
                "request_count": totals.count,
                "total_bytes": totals.bytes_,
            }
            for (bucket, branch, code), totals in hier_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(HierarchyMinuteAggregate),
            rows,
            index_elements=[
                HierarchyMinuteAggregate.bucket_ts,
                HierarchyMinuteAggregate.branch,
                HierarchyMinuteAggregate.hierarchy_code,
            ],
            sum_columns=["request_count", "total_bytes"],
        )

    async def _bulk_upsert_user_category(
        self,
        session: AsyncSession,
        usercat_buckets: dict[tuple[datetime, str, str, DomainCategoryLabel], _CountBytes],
    ) -> None:
        if not usercat_buckets:
            return
        rows = [
            {
                "bucket_ts": bucket,
                "branch": branch,
                "user": user,
                "category": category,
                "request_count": totals.count,
                "total_bytes": totals.bytes_,
            }
            for (bucket, branch, user, category), totals in usercat_buckets.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(UserCategoryMinuteAggregate),
            rows,
            index_elements=[
                UserCategoryMinuteAggregate.bucket_ts,
                UserCategoryMinuteAggregate.branch,
                UserCategoryMinuteAggregate.user,
                UserCategoryMinuteAggregate.category,
            ],
            sum_columns=["request_count", "total_bytes"],
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
            declared_table(DomainMinuteAggregate),
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
            declared_table(ClientCategoryMinuteAggregate),
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
            declared_table(ClientMinuteAggregate),
            rows,
            index_elements=[
                ClientMinuteAggregate.bucket_ts,
                ClientMinuteAggregate.client_ip,
                ClientMinuteAggregate.branch,
                func.coalesce(ClientMinuteAggregate.user, literal_column("''")),
            ],
            sum_columns=["request_count", "blocked_count", "total_bytes"],
        )
