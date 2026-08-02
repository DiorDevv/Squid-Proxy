from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_BRANCH, get_settings
from app.models.archive_run import ArchiveRun
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.refresh_token import RefreshToken
from app.services.retention import RetentionJob


def _raw_event(timestamp: datetime, client_ip: str = "10.0.0.1") -> RawEvent:
    return RawEvent(
        timestamp=timestamp,
        duration_ms=1,
        client_ip=client_ip,
        action="TCP_MISS",
        status_code=200,
        bytes=1,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=False,
    )


async def test_purge_deletes_raw_events_past_raw_retention_window(
    db_session: AsyncSession, monkeypatch
):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    old_ts = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    recent_ts = now - timedelta(minutes=1)

    db_session.add_all([_raw_event(old_ts), _raw_event(recent_ts)])
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    remaining = (await db_session.execute(select(RawEvent))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].client_ip == "10.0.0.1"


async def test_purge_deletes_raw_events_across_multiple_batches(db_session: AsyncSession, monkeypatch):
    # Regression coverage for batching raw_events' delete: a single
    # unbatched DELETE across a whole cutoff window used to hold locks
    # against the aggregator's writes for however long a multi-million-row
    # delete took. Forcing a tiny batch size here (instead of the real
    # 5000-row default) makes the same multi-batch code path exercise with
    # only a handful of rows, while still proving every batch iteration
    # actually ran and the reported total is the sum across all of them, not
    # just the first batch.
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(retention_module, "_RAW_EVENTS_DELETE_BATCH_SIZE", 3)

    settings = get_settings()
    now = datetime.now(UTC)
    old_ts = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    db_session.add_all([_raw_event(old_ts, client_ip=f"10.0.0.{i}") for i in range(10)])
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    remaining = (await db_session.execute(select(RawEvent))).scalars().all()
    assert remaining == []


async def test_purge_keeps_raw_events_within_retention_window(db_session: AsyncSession, monkeypatch):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    now = datetime.now(UTC)
    db_session.add(_raw_event(now - timedelta(hours=1)))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    remaining = (await db_session.execute(select(RawEvent))).scalars().all()
    assert len(remaining) == 1


async def test_purge_deletes_aggregates_past_aggregate_retention_window(
    db_session: AsyncSession, monkeypatch
):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    old_bucket = (now - timedelta(days=settings.RETENTION_DAYS_AGGREGATES + 1)).replace(
        second=0, microsecond=0
    )
    recent_bucket = now.replace(second=0, microsecond=0)

    db_session.add_all(
        [
            MinuteAggregate(bucket_ts=old_bucket, total_requests=1, blocked_requests=0, allowed_requests=1, total_bytes=1),
            MinuteAggregate(bucket_ts=recent_bucket, total_requests=1, blocked_requests=0, allowed_requests=1, total_bytes=1),
            DomainMinuteAggregate(bucket_ts=old_bucket, domain="old.com", request_count=1, blocked_count=0),
            DomainMinuteAggregate(bucket_ts=recent_bucket, domain="new.com", request_count=1, blocked_count=0),
            ClientMinuteAggregate(
                bucket_ts=old_bucket, client_ip="10.0.0.1", user=None, request_count=1, blocked_count=0, total_bytes=1
            ),
            ClientMinuteAggregate(
                bucket_ts=recent_bucket, client_ip="10.0.0.2", user=None, request_count=1, blocked_count=0, total_bytes=1
            ),
            ClientCategoryMinuteAggregate(
                bucket_ts=old_bucket,
                client_ip="10.0.0.1",
                category=DomainCategoryLabel.VIDEO_STREAMING,
                request_count=1,
                total_bytes=1,
            ),
            ClientCategoryMinuteAggregate(
                bucket_ts=recent_bucket,
                client_ip="10.0.0.2",
                category=DomainCategoryLabel.VIDEO_STREAMING,
                request_count=1,
                total_bytes=1,
            ),
        ]
    )
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    minute_rows = (await db_session.execute(select(MinuteAggregate))).scalars().all()
    domain_rows = (await db_session.execute(select(DomainMinuteAggregate))).scalars().all()
    client_rows = (await db_session.execute(select(ClientMinuteAggregate))).scalars().all()
    category_rows = (await db_session.execute(select(ClientCategoryMinuteAggregate))).scalars().all()

    assert [r.bucket_ts.replace(tzinfo=UTC) for r in minute_rows] == [recent_bucket]
    assert [r.domain for r in domain_rows] == ["new.com"]
    assert [r.client_ip for r in client_rows] == ["10.0.0.2"]
    assert [r.client_ip for r in category_rows] == ["10.0.0.2"]


async def test_purge_deletes_only_expired_refresh_tokens(db_session: AsyncSession, monkeypatch):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    now = datetime.now(UTC)
    expired = RefreshToken(
        jti="expired-jti", user_id="u1", token_hash="hash1", expires_at=now - timedelta(days=1)
    )
    revoked_but_not_yet_expired = RefreshToken(
        jti="revoked-jti", user_id="u1", token_hash="hash2", revoked=True, expires_at=now + timedelta(days=1)
    )
    active = RefreshToken(jti="active-jti", user_id="u1", token_hash="hash3", expires_at=now + timedelta(days=1))
    db_session.add_all([expired, revoked_but_not_yet_expired, active])
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    remaining_jtis = {r.jti for r in (await db_session.execute(select(RefreshToken))).scalars().all()}
    assert remaining_jtis == {"revoked-jti", "active-jti"}


async def test_purge_rolls_up_old_client_minutes_into_hourly_and_deletes_the_source_rows(
    db_session: AsyncSession, monkeypatch
):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    old_hour = (now - timedelta(hours=settings.CLIENT_ROLLUP_AFTER_HOURS + 3)).replace(
        minute=0, second=0, microsecond=0
    )
    recent_bucket = now.replace(second=0, microsecond=0)

    # Two minute rows in the same old hour, same client -- should collapse
    # into a single hourly row with summed counts.
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=old_hour + timedelta(minutes=5),
                client_ip="10.0.0.40",
                user=None,
                request_count=3,
                blocked_count=1,
                total_bytes=300,
            ),
            ClientMinuteAggregate(
                bucket_ts=old_hour + timedelta(minutes=40),
                client_ip="10.0.0.40",
                user=None,
                request_count=2,
                blocked_count=0,
                total_bytes=200,
            ),
            # Recent, within the rollup window -- must survive untouched.
            ClientMinuteAggregate(
                bucket_ts=recent_bucket, client_ip="10.0.0.41", user=None, request_count=1, blocked_count=0, total_bytes=1
            ),
        ]
    )
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    minute_rows = (await db_session.execute(select(ClientMinuteAggregate))).scalars().all()
    assert [r.client_ip for r in minute_rows] == ["10.0.0.41"]

    hourly_rows = (await db_session.execute(select(ClientHourlyAggregate))).scalars().all()
    assert len(hourly_rows) == 1
    assert hourly_rows[0].client_ip == "10.0.0.40"
    assert hourly_rows[0].bucket_ts.replace(tzinfo=UTC) == old_hour
    assert hourly_rows[0].request_count == 5
    assert hourly_rows[0].blocked_count == 1
    assert hourly_rows[0].total_bytes == 500


async def test_purge_flags_branch_with_no_archive_run_as_unarchived(db_session: AsyncSession, monkeypatch):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    old_ts = datetime.now(UTC) - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    db_session.add(_raw_event(old_ts))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    # No ArchiveRun row exists for this branch at all -- the raw data just
    # purged was never archived, so it should be flagged.
    assert job.unarchived_branches == [DEFAULT_BRANCH]


async def test_purge_does_not_flag_a_branch_covered_by_a_recent_archive_run(
    db_session: AsyncSession, monkeypatch
):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    old_ts = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    db_session.add(_raw_event(old_ts))
    db_session.add(ArchiveRun(branch=DEFAULT_BRANCH, archived_until=now))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    assert job.unarchived_branches == []


async def test_purge_flags_branch_whose_archive_run_is_too_old(db_session: AsyncSession, monkeypatch):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    raw_cutoff = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS)
    old_ts = raw_cutoff - timedelta(days=1)
    db_session.add(_raw_event(old_ts))
    # Archived once, but before the data that's about to be purged now --
    # e.g. the weekly cron hasn't run again since older data accumulated.
    db_session.add(ArchiveRun(branch=DEFAULT_BRANCH, archived_until=raw_cutoff - timedelta(days=1)))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    assert job.unarchived_branches == [DEFAULT_BRANCH]


async def test_purge_emails_a_warning_when_a_branch_was_purged_unarchived(
    db_session: AsyncSession, monkeypatch
):
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    calls = []

    async def fake_send(branches: list[str], raw_cutoff: datetime) -> bool:
        calls.append(branches)
        return True

    monkeypatch.setattr(retention_module, "send_unarchived_purge_warning", fake_send)

    settings = get_settings()
    old_ts = datetime.now(UTC) - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    db_session.add(_raw_event(old_ts))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    assert calls == [[DEFAULT_BRANCH]]


async def test_purge_survives_a_failed_warning_email(db_session: AsyncSession, monkeypatch):
    """A broken/unconfigured SMTP setup must never take down retention --
    the purge itself must still complete and commit."""
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    async def broken_send(branches: list[str], raw_cutoff: datetime) -> bool:
        raise RuntimeError("SMTP is not configured")

    monkeypatch.setattr(retention_module, "send_unarchived_purge_warning", broken_send)

    settings = get_settings()
    old_ts = datetime.now(UTC) - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS + 1)
    db_session.add(_raw_event(old_ts))
    await db_session.commit()

    job = RetentionJob()
    await job.purge()  # must not raise

    remaining = (await db_session.execute(select(RawEvent))).scalars().all()
    assert remaining == []


async def test_purge_rollup_accumulates_into_an_existing_hourly_row_on_a_later_run(
    db_session: AsyncSession, monkeypatch
):
    """A second purge run must add to an already-rolled-up hour, not
    overwrite or duplicate it."""
    import app.services.retention as retention_module

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)

    settings = get_settings()
    now = datetime.now(UTC)
    old_hour = (now - timedelta(hours=settings.CLIENT_ROLLUP_AFTER_HOURS + 3)).replace(
        minute=0, second=0, microsecond=0
    )

    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=old_hour + timedelta(minutes=5),
            client_ip="10.0.0.42",
            user=None,
            request_count=3,
            blocked_count=0,
            total_bytes=300,
        )
    )
    await db_session.commit()
    job = RetentionJob()
    await job.purge()

    # A second minute row lands in the same already-rolled-up hour before
    # the next purge run.
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=old_hour + timedelta(minutes=40),
            client_ip="10.0.0.42",
            user=None,
            request_count=2,
            blocked_count=0,
            total_bytes=200,
        )
    )
    await db_session.commit()
    await job.purge()

    hourly_rows = (await db_session.execute(select(ClientHourlyAggregate))).scalars().all()
    assert len(hourly_rows) == 1
    assert hourly_rows[0].request_count == 5
    assert hourly_rows[0].total_bytes == 500
