"""Tests for app.services.db_upsert.bulk_upsert_sum -- including the
chunking that keeps a single flush's worth of rows from overflowing
SQLite's per-statement bound-parameter limit, which a real ~500k-event
burst hit in practice (see app/services/db_upsert.py's module docstring)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_aggregate import DomainMinuteAggregate
from app.services import db_upsert

BUCKET = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _row(domain: str, request_count: int = 1, blocked_count: int = 0, total_bytes: int = 100) -> dict:
    return {
        "bucket_ts": BUCKET,
        "domain": domain,
        "branch": "default",
        "request_count": request_count,
        "blocked_count": blocked_count,
        "total_bytes": total_bytes,
    }


async def test_bulk_upsert_sum_inserts_new_rows(db_session: AsyncSession):
    await db_upsert.bulk_upsert_sum(
        db_session,
        DomainMinuteAggregate.__table__,
        [_row("a.example"), _row("b.example", request_count=3, total_bytes=300)],
        index_elements=["bucket_ts", "domain", "branch"],
        sum_columns=["request_count", "blocked_count", "total_bytes"],
    )
    await db_session.commit()

    rows = (await db_session.execute(select(DomainMinuteAggregate))).scalars().all()
    by_domain = {r.domain: r for r in rows}
    assert by_domain["a.example"].request_count == 1
    assert by_domain["b.example"].request_count == 3
    assert by_domain["b.example"].total_bytes == 300


async def test_bulk_upsert_sum_sums_on_conflict_instead_of_overwriting(db_session: AsyncSession):
    await db_upsert.bulk_upsert_sum(
        db_session,
        DomainMinuteAggregate.__table__,
        [_row("a.example", request_count=2, total_bytes=200)],
        index_elements=["bucket_ts", "domain", "branch"],
        sum_columns=["request_count", "blocked_count", "total_bytes"],
    )
    await db_session.commit()

    # Second flush touching the same (bucket, domain, branch) key must add
    # to the existing row, not replace it.
    await db_upsert.bulk_upsert_sum(
        db_session,
        DomainMinuteAggregate.__table__,
        [_row("a.example", request_count=5, total_bytes=500)],
        index_elements=["bucket_ts", "domain", "branch"],
        sum_columns=["request_count", "blocked_count", "total_bytes"],
    )
    await db_session.commit()

    row = (
        await db_session.execute(select(DomainMinuteAggregate).where(DomainMinuteAggregate.domain == "a.example"))
    ).scalar_one()
    assert row.request_count == 7
    assert row.total_bytes == 700


async def test_bulk_upsert_sum_chunks_large_batches_without_dropping_or_duplicating_rows(
    db_session: AsyncSession,
):
    """A single flush window touching enough distinct keys to exceed one
    statement's safe parameter budget must still persist every row exactly
    once, split across multiple statements inside the same transaction --
    reproduced against a real access.log burst as `sqlite3.OperationalError:
    too many SQL variables`, which then got the aggregator permanently stuck
    (every retry re-submitted the exact same oversized batch). This uses
    enough rows to force several batches at the module's configured
    _MAX_VARIABLES_PER_STATEMENT / 6-columns-per-row chunk size.
    """
    domain_count = 5 * (db_upsert._MAX_VARIABLES_PER_STATEMENT // 6)  # forces >= 5 chunks
    rows = [_row(f"domain-{i}.example", request_count=i + 1) for i in range(domain_count)]

    await db_upsert.bulk_upsert_sum(
        db_session,
        DomainMinuteAggregate.__table__,
        rows,
        index_elements=["bucket_ts", "domain", "branch"],
        sum_columns=["request_count", "blocked_count", "total_bytes"],
    )
    await db_session.commit()

    persisted = (await db_session.execute(select(DomainMinuteAggregate))).scalars().all()
    assert len(persisted) == domain_count
    by_domain = {r.domain: r.request_count for r in persisted}
    assert by_domain[f"domain-{domain_count - 1}.example"] == domain_count
    assert by_domain["domain-0.example"] == 1


async def test_bulk_upsert_sum_with_no_rows_is_a_noop(db_session: AsyncSession):
    await db_upsert.bulk_upsert_sum(
        db_session,
        DomainMinuteAggregate.__table__,
        [],
        index_elements=["bucket_ts", "domain", "branch"],
        sum_columns=["request_count", "blocked_count", "total_bytes"],
    )
    await db_session.commit()

    rows = (await db_session.execute(select(DomainMinuteAggregate))).scalars().all()
    assert rows == []
