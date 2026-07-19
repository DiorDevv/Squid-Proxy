from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
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
        ]
    )
    await db_session.commit()

    job = RetentionJob()
    await job.purge()

    minute_rows = (await db_session.execute(select(MinuteAggregate))).scalars().all()
    domain_rows = (await db_session.execute(select(DomainMinuteAggregate))).scalars().all()
    client_rows = (await db_session.execute(select(ClientMinuteAggregate))).scalars().all()

    assert [r.bucket_ts.replace(tzinfo=UTC) for r in minute_rows] == [recent_bucket]
    assert [r.domain for r in domain_rows] == ["new.com"]
    assert [r.client_ip for r in client_rows] == ["10.0.0.2"]


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
