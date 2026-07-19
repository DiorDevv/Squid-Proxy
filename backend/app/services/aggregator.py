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

from sqlalchemy import select

from app.insights import get_insights_provider
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import insights_service
from app.services.alerting import maybe_alert
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
class FlushResult:
    events_flushed: int = 0
    buckets_touched: set[datetime] = field(default_factory=set)


class Aggregator:
    def __init__(self, ring_buffer: RingBuffer, interval_seconds: int = 60) -> None:
        self.ring_buffer = ring_buffer
        self.interval_seconds = interval_seconds
        self._last_flushed_id = 0
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

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
        events = self.ring_buffer.events_since(self._last_flushed_id)
        if not events:
            return FlushResult()
        self._last_flushed_id = events[-1].id

        minute_buckets: dict[datetime, _MinuteTotals] = defaultdict(_MinuteTotals)
        domain_buckets: dict[tuple[datetime, str], _DomainTotals] = defaultdict(_DomainTotals)
        client_buckets: dict[tuple[datetime, str, str | None], _ClientTotals] = defaultdict(
            _ClientTotals
        )
        raw_rows: list[RawEvent] = []

        for stored in events:
            ev = stored.event
            bucket = self._bucket(ev.timestamp)

            mb = minute_buckets[bucket]
            mb.total += 1
            mb.bytes_ += ev.bytes
            if ev.blocked:
                mb.blocked += 1
            else:
                mb.allowed += 1

            if ev.domain:
                db = domain_buckets[(bucket, ev.domain)]
                db.count += 1
                db.bytes_ += ev.bytes
                if ev.blocked:
                    db.blocked += 1

            cb = client_buckets[(bucket, ev.client_ip, ev.user)]
            cb.count += 1
            cb.bytes_ += ev.bytes
            if ev.blocked:
                cb.blocked += 1

            raw_rows.append(
                RawEvent(
                    timestamp=ev.timestamp,
                    duration_ms=ev.duration_ms,
                    client_ip=ev.client_ip,
                    action=ev.action,
                    status_code=ev.status_code,
                    bytes=ev.bytes,
                    method=ev.method,
                    url=ev.url,
                    domain=ev.domain,
                    user=ev.user,
                    hierarchy=ev.hierarchy,
                    peer=ev.peer,
                    content_type=ev.content_type,
                    blocked=ev.blocked,
                )
            )

        async with AsyncSessionLocal() as session:
            for bucket, totals in minute_buckets.items():
                await self._upsert_minute(session, bucket, totals)
            for (bucket, domain), totals in domain_buckets.items():
                await self._upsert_domain(session, bucket, domain, totals)
            for (bucket, ip, user), totals in client_buckets.items():
                await self._upsert_client(session, bucket, ip, user, totals)
            session.add_all(raw_rows)
            await session.commit()

        logger.info(
            "Aggregator flush complete",
            extra={"events_flushed": len(events), "minute_buckets": len(minute_buckets)},
        )
        await self._run_insights(events)
        return FlushResult(events_flushed=len(events), buckets_touched=set(minute_buckets))

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

    async def _upsert_minute(self, session, bucket: datetime, totals: _MinuteTotals) -> None:
        row = (
            await session.execute(select(MinuteAggregate).where(MinuteAggregate.bucket_ts == bucket))
        ).scalar_one_or_none()
        if row is None:
            # Column defaults apply at flush time, not on construction, so
            # zero these explicitly -- otherwise the += below hits None.
            row = MinuteAggregate(
                bucket_ts=bucket, total_requests=0, blocked_requests=0, allowed_requests=0, total_bytes=0
            )
            session.add(row)
        row.total_requests += totals.total
        row.blocked_requests += totals.blocked
        row.allowed_requests += totals.allowed
        row.total_bytes += totals.bytes_

    async def _upsert_domain(
        self, session, bucket: datetime, domain: str, totals: _DomainTotals
    ) -> None:
        row = (
            await session.execute(
                select(DomainMinuteAggregate).where(
                    DomainMinuteAggregate.bucket_ts == bucket,
                    DomainMinuteAggregate.domain == domain,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = DomainMinuteAggregate(
                bucket_ts=bucket, domain=domain, request_count=0, blocked_count=0, total_bytes=0
            )
            session.add(row)
        row.request_count += totals.count
        row.blocked_count += totals.blocked
        row.total_bytes += totals.bytes_

    async def _upsert_client(
        self, session, bucket: datetime, client_ip: str, user: str | None, totals: _ClientTotals
    ) -> None:
        row = (
            await session.execute(
                select(ClientMinuteAggregate).where(
                    ClientMinuteAggregate.bucket_ts == bucket,
                    ClientMinuteAggregate.client_ip == client_ip,
                    ClientMinuteAggregate.user == user,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ClientMinuteAggregate(
                bucket_ts=bucket, client_ip=client_ip, user=user,
                request_count=0, blocked_count=0, total_bytes=0,
            )
            session.add(row)
        row.request_count += totals.count
        row.blocked_count += totals.blocked
        row.total_bytes += totals.bytes_
