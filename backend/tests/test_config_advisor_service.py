"""Tests for app/services/config_advisor_service.py."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.services import config_advisor_service

NOW = datetime.now(UTC).replace(second=0, microsecond=0)
BUCKET = NOW - timedelta(minutes=30)


def _minute(**kw: object) -> MinuteAggregate:
    base = dict(
        bucket_ts=BUCKET,
        branch="default",
        total_requests=0,
        blocked_requests=0,
        allowed_requests=0,
        total_bytes=0,
        hit_requests=0,
        miss_requests=0,
    )
    base.update(kw)
    return MinuteAggregate(**base)  # type: ignore[arg-type]


async def _codes(session: AsyncSession) -> set[str]:
    result = await config_advisor_service.analyze(session, branch=None)
    return {f.code for f in result.findings}


async def test_quiet_when_below_min_requests(db_session: AsyncSession):
    db_session.add(_minute(total_requests=50, allowed_requests=50))
    await db_session.commit()
    result = await config_advisor_service.analyze(db_session, branch=None)
    assert result.findings == []
    assert result.window_hours == 24


async def test_healthy_deployment_gets_no_findings(db_session: AsyncSession):
    db_session.add_all(
        [
            _minute(
                total_requests=5000,
                blocked_requests=250,  # ~5% deny
                allowed_requests=4750,
                hit_requests=1500,
                miss_requests=2500,  # ~37% hit ratio
            ),
        ]
    )
    # authenticated users, spread across domains, nothing sensitive allowed
    db_session.add_all(
        [
            ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice", request_count=2500, blocked_count=0, total_bytes=0),
            ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.2", branch="default", user="bob", request_count=2500, blocked_count=0, total_bytes=0),
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="github.com", branch="default", request_count=2500, blocked_count=0, total_bytes=0),
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="cnn.com", branch="default", request_count=2500, blocked_count=0, total_bytes=0),
        ]
    )
    await db_session.commit()
    assert await _codes(db_session) == set()


async def test_flags_no_caching(db_session: AsyncSession):
    db_session.add(
        _minute(total_requests=5000, allowed_requests=4900, blocked_requests=100, hit_requests=5, miss_requests=3000)
    )
    db_session.add(ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice", request_count=5000, blocked_count=0, total_bytes=0))
    await db_session.commit()
    assert "no_caching" in await _codes(db_session)


async def test_flags_no_denies(db_session: AsyncSession):
    db_session.add(
        _minute(total_requests=5000, allowed_requests=5000, blocked_requests=0, hit_requests=2000, miss_requests=2000)
    )
    db_session.add(ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice", request_count=5000, blocked_count=0, total_bytes=0))
    await db_session.commit()
    assert "no_denies" in await _codes(db_session)


async def test_flags_no_proxy_auth(db_session: AsyncSession):
    db_session.add(
        _minute(total_requests=5000, allowed_requests=4750, blocked_requests=250, hit_requests=2000, miss_requests=2000)
    )
    db_session.add(
        ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user=None, request_count=5000, blocked_count=0, total_bytes=0)
    )
    await db_session.commit()
    assert "no_proxy_auth" in await _codes(db_session)


async def test_flags_sensitive_allowed(db_session: AsyncSession):
    db_session.add(
        _minute(total_requests=5000, allowed_requests=4750, blocked_requests=250, hit_requests=2000, miss_requests=2000)
    )
    db_session.add_all(
        [
            ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice", request_count=5000, blocked_count=0, total_bytes=0),
            # pokerstars.com -> gambling (inferred); allowed (blocked_count 0)
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="pokerstars.com", branch="default", request_count=200, blocked_count=0, total_bytes=0),
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="github.com", branch="default", request_count=4800, blocked_count=0, total_bytes=0),
        ]
    )
    await db_session.commit()
    assert "sensitive_allowed" in await _codes(db_session)


async def test_flags_single_domain_dominant(db_session: AsyncSession):
    db_session.add(
        _minute(total_requests=5000, allowed_requests=4750, blocked_requests=250, hit_requests=2000, miss_requests=2000)
    )
    db_session.add_all(
        [
            ClientMinuteAggregate(bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice", request_count=5000, blocked_count=0, total_bytes=0),
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="one.example", branch="default", request_count=4800, blocked_count=0, total_bytes=0),
            DomainMinuteAggregate(bucket_ts=BUCKET, domain="two.example", branch="default", request_count=200, blocked_count=0, total_bytes=0),
        ]
    )
    await db_session.commit()
    result = await config_advisor_service.analyze(db_session, branch=None)
    dominant = next(f for f in result.findings if f.code == "single_domain_dominant")
    assert dominant.detail == "one.example"
