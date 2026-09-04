"""Tests for app/services/squid_ops_service.py -- the Analytics section's
Squid-operational views (Traffic & cache, Blocks, Who)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.ops_aggregate import (
    HttpMinuteAggregate,
    ResultCodeMinuteAggregate,
    UserCategoryMinuteAggregate,
)
from app.schemas.analytics import TrendGranularity
from app.services import squid_ops_service
from app.services.aggregator import Aggregator
from app.services.event_store import RingBuffer
from app.services.log_parser import parse_line

NOW = datetime.now(UTC).replace(second=0, microsecond=0)
SINCE = NOW - timedelta(hours=1)
BUCKET = SINCE + timedelta(minutes=1)
_BUCKET_EPOCH = BUCKET.timestamp()


def _line(action_status: str, *, ms: int = 45, method: str = "GET", user: str = "alice",
          hierarchy: str = "HIER_DIRECT/93.184.216.34", client: str = "10.0.0.5",
          domain: str = "example.com", size: int = 1024) -> str:
    return (
        f"{_BUCKET_EPOCH:.3f} {ms} {client} {action_status} {size} {method} "
        f"http://{domain}/ {user} {hierarchy} text/html"
    )


async def test_result_codes_and_response_time_from_aggregator_flush(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.services.aggregator as aggregator_module

    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)

    ring = RingBuffer(max_events=100)
    ring.append(parse_line(_line("TCP_HIT/200", ms=20)))
    ring.append(parse_line(_line("TCP_HIT/200", ms=40)))
    ring.append(parse_line(_line("TCP_MISS/200", ms=800)))
    ring.append(parse_line(_line("TCP_DENIED/403", ms=5, method="CONNECT")))
    ring.append(parse_line(_line("TCP_TUNNEL/200", ms=15000, method="CONNECT")))
    await Aggregator(ring_buffer=ring, interval_seconds=60).flush()

    async with session_factory() as session:
        codes = await squid_ops_service.get_result_codes(
            session, SINCE, NOW, TrendGranularity.HOUR, branch=None
        )
        labels = {c.label: c.request_count for c in codes.codes}
        assert labels["TCP_HIT"] == 2
        assert labels["TCP_MISS"] == 1
        assert labels["TCP_DENIED"] == 1
        assert labels["TCP_TUNNEL"] == 1
        # 2 hits / (2 hits + 1 miss)
        assert round(codes.hit_ratio, 2) == 0.67
        assert round(codes.denied_ratio, 2) == 0.2
        assert round(codes.tunnel_ratio, 2) == 0.2

        rt = await squid_ops_service.get_response_time(
            session, SINCE, NOW, TrendGranularity.HOUR, branch=None
        )
        assert rt.sample_count == 5
        # bands: <100ms x3 (20,40,5), 300ms-1s x1 (800), >=10s x1 (15000)
        band_by_label = {b.label: b.request_count for b in rt.bands}
        assert band_by_label["<100ms"] == 3
        assert band_by_label["300ms-1s"] == 1
        assert band_by_label[">=10s"] == 1
        assert rt.overall_p50 <= 100  # median falls in the first (<100ms) band
        assert rt.overall_p99 >= 10000  # the 15s outlier

        http = await squid_ops_service.get_http_breakdown(session, SINCE, NOW, branch=None)
        methods = {m.label: m.request_count for m in http.methods}
        assert methods["GET"] == 3
        assert methods["CONNECT"] == 2
        assert http.denied_403 == 1

        hier = await squid_ops_service.get_hierarchy_breakdown(session, SINCE, NOW, branch=None)
        assert hier.codes[0].label == "HIER_DIRECT"
        assert hier.codes[0].request_count == 5


async def test_percentile_from_histogram_interpolates():
    # 10 samples all in the 300ms-1s band -> p50 lands mid-band
    counts = [0, 0, 10, 0, 0, 0]
    p50 = squid_ops_service._percentile_from_hist(counts, 50)
    assert 300 <= p50 <= 1000
    # p99 near the top of that band
    assert squid_ops_service._percentile_from_hist(counts, 99) > p50
    # empty -> 0
    assert squid_ops_service._percentile_from_hist([0] * 6, 95) == 0.0


async def test_actor_leaderboard_prefers_users_and_reports_top_category(db_session: AsyncSession):
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice",
                request_count=100, blocked_count=10, total_bytes=5000,
            ),
            ClientMinuteAggregate(
                bucket_ts=BUCKET, client_ip="10.0.0.2", branch="default", user="bob",
                request_count=40, blocked_count=1, total_bytes=2000,
            ),
            UserCategoryMinuteAggregate(
                bucket_ts=BUCKET, branch="default", user="alice",
                category=DomainCategoryLabel.VIDEO_STREAMING, request_count=80, total_bytes=4000,
            ),
            UserCategoryMinuteAggregate(
                bucket_ts=BUCKET, branch="default", user="alice",
                category=DomainCategoryLabel.NEWS, request_count=20, total_bytes=1000,
            ),
        ]
    )
    await db_session.commit()

    board = await squid_ops_service.get_actor_leaderboard(
        db_session, SINCE, NOW, branch=None, limit=25, sort="requests"
    )
    assert board.actor_kind == "user"
    assert [r.actor for r in board.rows] == ["alice", "bob"]
    alice = board.rows[0]
    assert alice.request_count == 100
    assert alice.blocked_ratio == 0.1
    assert alice.top_category == DomainCategoryLabel.VIDEO_STREAMING


async def test_actor_leaderboard_falls_back_to_client_ip_without_auth(db_session: AsyncSession):
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=BUCKET, client_ip="192.168.1.9", branch="default", user=None,
            request_count=12, blocked_count=0, total_bytes=900,
        )
    )
    await db_session.commit()

    board = await squid_ops_service.get_actor_leaderboard(
        db_session, SINCE, NOW, branch=None, limit=25, sort="requests"
    )
    assert board.actor_kind == "client_ip"
    assert board.rows[0].actor == "192.168.1.9"
    assert board.rows[0].is_user is False


async def test_denials_splits_reasons_from_aggregates(db_session: AsyncSession):
    db_session.add_all(
        [
            MinuteAggregate(
                bucket_ts=BUCKET, branch="default", total_requests=100,
                blocked_requests=30, allowed_requests=70,
            ),
            HttpMinuteAggregate(
                bucket_ts=BUCKET, branch="default", method="GET", status_code=403,
                request_count=12, total_bytes=0,
            ),
            HttpMinuteAggregate(
                bucket_ts=BUCKET, branch="default", method="GET", status_code=407,
                request_count=5, total_bytes=0,
            ),
            ResultCodeMinuteAggregate(
                bucket_ts=BUCKET, branch="default", action="TCP_DENIED",
                request_count=12, total_bytes=0,
            ),
            DomainMinuteAggregate(
                bucket_ts=BUCKET, domain="pokerstars.com", branch="default",
                request_count=12, blocked_count=12, total_bytes=800,
            ),
        ]
    )
    await db_session.commit()

    denials = await squid_ops_service.get_denials(
        db_session, SINCE, NOW, TrendGranularity.HOUR, branch=None
    )
    assert denials.acl_denied == 12  # max(403 count, TCP_DENIED count)
    assert denials.proxy_auth == 5
    assert denials.other_blocked == 30 - 12 - 5  # remainder of blocked_requests
    assert denials.total_denied == 30
    assert denials.top_domains[0].domain == "pokerstars.com"
    assert denials.top_categories[0].category == DomainCategoryLabel.GAMBLING


async def test_new_entities_reports_first_seen_within_window(db_session: AsyncSession):
    older = SINCE - timedelta(hours=3)  # before the [SINCE, NOW] window
    db_session.add_all(
        [
            # "veteran" first seen before the window -> not new
            ClientMinuteAggregate(
                bucket_ts=older, client_ip="10.0.0.1", branch="default", user="veteran",
                request_count=5, blocked_count=0, total_bytes=100,
            ),
            # "newbie" first seen inside the window -> new
            ClientMinuteAggregate(
                bucket_ts=BUCKET, client_ip="10.0.0.2", branch="default", user="newbie",
                request_count=5, blocked_count=0, total_bytes=100,
            ),
        ]
    )
    await db_session.commit()

    result = await squid_ops_service.get_new_entities(db_session, SINCE, NOW, branch=None)
    assert "newbie" in result.new_users
    assert "veteran" not in result.new_users
    assert "10.0.0.2" in result.new_clients
    assert "10.0.0.1" not in result.new_clients


async def test_actor_detail_reads_category_split_and_hourly(db_session: AsyncSession):
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default", user="alice",
                request_count=50, blocked_count=5, total_bytes=3000,
            ),
            ClientCategoryMinuteAggregate(
                bucket_ts=BUCKET, client_ip="10.0.0.1", branch="default",
                category=DomainCategoryLabel.SOCIAL_MEDIA, request_count=30, total_bytes=2000,
            ),
            UserCategoryMinuteAggregate(
                bucket_ts=BUCKET, branch="default", user="alice",
                category=DomainCategoryLabel.SOCIAL_MEDIA, request_count=30, total_bytes=2000,
            ),
        ]
    )
    await db_session.commit()

    detail = await squid_ops_service.get_actor_detail(
        db_session, "alice", is_user=True, since=SINCE, until=NOW, branch=None
    )
    assert detail.request_count == 50
    assert detail.blocked_count == 5
    assert detail.categories[0].category == DomainCategoryLabel.SOCIAL_MEDIA
    assert sum(detail.hourly) == 50
    assert len(detail.hourly) == 24


def test_build_ingest_health_reshapes_health_snapshot():
    snapshot = {
        "aggregator_backlog_ratio": 0.12,
        "aggregator_events_likely_lost": False,
        "log_sources": [
            {"branch": "hq", "alive": True, "lines_seen": 1000, "lines_parsed": 1000,
             "parse_failure_rate": 0.0},
            {"branch": "wh", "alive": False, "lines_seen": 500, "lines_parsed": 100,
             "parse_failure_rate": 0.8},
        ],
    }
    health = squid_ops_service.build_ingest_health(snapshot)
    assert health.aggregator_backlog_ratio == 0.12
    assert {b.branch for b in health.branches} == {"hq", "wh"}
    wh = next(b for b in health.branches if b.branch == "wh")
    assert wh.tailer_alive is False
    assert wh.parse_failure_rate == 0.8
