"""Tests for app/services/analytics_service.py -- the read-side rollups
behind the Analytics section (`/api/analytics/*`)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LogSource, RiskModelConfig, Settings
from app.models.alert_settings import AlertSettings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.schemas.analytics import HeatmapCell, TrendGranularity, TrendMetric
from app.services import analytics_service


def _minute(**kw: object) -> MinuteAggregate:
    base = dict(total_requests=0, blocked_requests=0, allowed_requests=0, total_bytes=0)
    base.update(kw)
    return MinuteAggregate(**base)  # type: ignore[arg-type]


async def test_overview_computes_current_vs_previous_and_pct_change(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    prev_since = since - timedelta(hours=1)

    db_session.add_all(
        [
            # current window: 100 total, 20 blocked
            _minute(bucket_ts=since + timedelta(minutes=1), total_requests=100, blocked_requests=20, allowed_requests=80, total_bytes=1000),
            # previous window: 50 total, 5 blocked
            _minute(bucket_ts=prev_since + timedelta(minutes=1), total_requests=50, blocked_requests=5, allowed_requests=45, total_bytes=400),
        ]
    )
    await db_session.commit()

    overview = await analytics_service.get_overview(db_session, since, now, branch=None)

    metrics = {m.metric: m for m in overview.metrics}
    assert metrics["total_requests"].current == 100
    assert metrics["total_requests"].previous == 50
    assert metrics["total_requests"].pct_change == 100.0
    assert metrics["blocked_requests"].current == 20
    assert round(overview.blocked_ratio, 2) == 0.20


async def test_overview_pct_change_is_none_when_previous_zero(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    db_session.add(_minute(bucket_ts=since + timedelta(minutes=1), total_requests=10, allowed_requests=10))
    await db_session.commit()

    overview = await analytics_service.get_overview(db_session, since, now, branch=None)
    metrics = {m.metric: m for m in overview.metrics}
    assert metrics["total_requests"].previous == 0
    assert metrics["total_requests"].pct_change is None


async def test_category_trend_orders_categories_by_total_and_buckets(db_session: AsyncSession):
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    since = now - timedelta(hours=3)
    db_session.add_all(
        [
            # youtube.com -> video_streaming (inferred), github.com -> work_tools
            DomainMinuteAggregate(bucket_ts=since + timedelta(minutes=5), domain="youtube.com", request_count=10, total_bytes=5000),
            DomainMinuteAggregate(bucket_ts=since + timedelta(minutes=65), domain="youtube.com", request_count=10, total_bytes=5000),
            DomainMinuteAggregate(bucket_ts=since + timedelta(minutes=5), domain="github.com", request_count=5, total_bytes=100),
        ]
    )
    await db_session.commit()

    trend = await analytics_service.get_category_trend(
        db_session, since, now, TrendGranularity.HOUR, TrendMetric.BYTES, branch=None
    )
    assert trend.categories[0].value == "video_streaming"
    assert "work_tools" in [c.value for c in trend.categories]
    # two distinct hour buckets for youtube
    assert len(trend.points) == 2
    assert trend.points[0].values["video_streaming"] == 5000


async def test_branch_breakdown_sorts_and_scopes(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(
        analytics_service,
        "get_settings",
        lambda: Settings(
            LOG_SOURCES=[
                LogSource(branch="hq", path="/x/hq.log"),
                LogSource(branch="warehouse", path="/x/wh.log"),
            ]
        ),
    )
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    db_session.add_all(
        [
            _minute(bucket_ts=since + timedelta(minutes=1), branch="hq", total_requests=200, blocked_requests=10, allowed_requests=190),
            _minute(bucket_ts=since + timedelta(minutes=1), branch="warehouse", total_requests=30, blocked_requests=15, allowed_requests=15),
        ]
    )
    await db_session.commit()

    result = await analytics_service.get_branch_breakdown(db_session, since, now, branch=None)
    assert [r.branch for r in result.rows] == ["hq", "warehouse"]
    assert result.rows[0].total_requests == 200
    assert round(result.rows[1].blocked_ratio, 2) == 0.5

    # A branch-scoped caller only ever gets their own row.
    scoped = await analytics_service.get_branch_breakdown(db_session, since, now, branch="warehouse")
    assert [r.branch for r in scoped.rows] == ["warehouse"]


async def test_branch_risk_high_blocked_ratio_and_anomalies_raise_score(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    db_session.add_all(
        [
            _minute(bucket_ts=since + timedelta(minutes=1), branch="default", total_requests=100, blocked_requests=60, allowed_requests=40),
            AnomalyEvent(
                generated_at=since + timedelta(minutes=2),
                title="x",
                description="y",
                severity=AnomalySeverity.CRITICAL,
                branch="default",
                kind="client_quota_exceeded",
            ),
        ]
    )
    await db_session.commit()

    result = await analytics_service.get_branch_risk(db_session, since, now, branch=None)
    row = result.rows[0]
    assert row.branch == "default"
    assert row.band in ("medium", "high")
    assert row.score > 40
    assert row.anomaly_count == 1
    keys = {s.key for s in row.signals}
    assert keys == {
        "blocked_ratio",
        "sensitive_traffic",
        "anomalies",
        "quota_breaches",
        "uncategorized_domains",
    }
    # signal contributions sum (approximately) to the composite score
    assert abs(sum(s.score for s in row.signals) - row.score) < 0.05


async def test_branch_risk_quiet_branch_is_low(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    db_session.add(_minute(bucket_ts=since + timedelta(minutes=1), total_requests=100, blocked_requests=1, allowed_requests=99))
    await db_session.commit()

    result = await analytics_service.get_branch_risk(db_session, since, now, branch=None)
    assert result.rows[0].band == "low"
    assert result.rows[0].score < 40


async def test_activity_heatmap_buckets_by_weekday_and_hour(db_session: AsyncSession):
    # A fixed known instant: 2026-09-02 is a Wednesday (weekday() == 2).
    ts = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)
    db_session.add_all(
        [
            _minute(bucket_ts=ts, total_requests=40, blocked_requests=10, allowed_requests=30),
            _minute(bucket_ts=ts.replace(minute=45), total_requests=10, blocked_requests=5, allowed_requests=5),
        ]
    )
    await db_session.commit()

    result = await analytics_service.get_activity_heatmap(
        db_session, ts - timedelta(hours=1), ts + timedelta(hours=1), branch=None, blocked_only=False
    )
    assert result.cells == [HeatmapCell(weekday=2, hour=14, value=50)]
    assert result.max_value == 50

    blocked = await analytics_service.get_activity_heatmap(
        db_session, ts - timedelta(hours=1), ts + timedelta(hours=1), branch=None, blocked_only=True
    )
    assert blocked.cells[0].value == 15


async def test_activity_heatmap_applies_tz_offset(db_session: AsyncSession):
    # 2026-09-02 23:30 UTC is still Wednesday (weekday 2) at hour 23; shifted
    # +5h it becomes Thursday (weekday 3) at hour 04.
    ts = datetime(2026, 9, 2, 23, 30, tzinfo=UTC)
    db_session.add(_minute(bucket_ts=ts, total_requests=7, allowed_requests=7))
    await db_session.commit()

    utc = await analytics_service.get_activity_heatmap(
        db_session, ts - timedelta(hours=1), ts + timedelta(hours=1), branch=None, blocked_only=False
    )
    assert utc.cells == [HeatmapCell(weekday=2, hour=23, value=7)]
    assert utc.tz_offset_minutes == 0

    local = await analytics_service.get_activity_heatmap(
        db_session,
        ts - timedelta(hours=1),
        ts + timedelta(hours=1),
        branch=None,
        blocked_only=False,
        tz_offset_minutes=300,
    )
    assert local.cells == [HeatmapCell(weekday=3, hour=4, value=7)]
    assert local.tz_offset_minutes == 300


async def test_category_trend_coarsens_hour_to_day_past_bucket_cap(
    db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        analytics_service,
        "get_settings",
        lambda: Settings(CATEGORY_TREND_MAX_BUCKETS=24),
    )
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    since = now - timedelta(days=3)  # 72 hours > 24-bucket cap
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=since + timedelta(hours=1), domain="youtube.com", request_count=5, total_bytes=1000),
            DomainMinuteAggregate(bucket_ts=since + timedelta(hours=26), domain="youtube.com", request_count=5, total_bytes=1000),
        ]
    )
    await db_session.commit()

    trend = await analytics_service.get_category_trend(
        db_session, since, now, TrendGranularity.HOUR, TrendMetric.BYTES, branch=None
    )
    # asked for HOUR, got DAY because the window is too wide
    assert trend.granularity == TrendGranularity.DAY
    assert all(point.bucket_ts.hour == 0 for point in trend.points)


async def test_branch_risk_weights_are_config_overridable(db_session: AsyncSession, monkeypatch):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    db_session.add(
        _minute(
            bucket_ts=since + timedelta(minutes=1),
            branch="default",
            total_requests=100,
            blocked_requests=40,
            allowed_requests=60,
        )
    )
    await db_session.commit()

    # blocked_ratio = 0.40, which is exactly the default ceiling -> that
    # signal normalizes to 1.0. With only its weight (0.30) it contributes
    # 30 pts. Doubling the ceiling halves the contribution to ~15.
    base = await analytics_service.get_branch_risk(db_session, since, now, branch=None)
    base_blocked = next(s for s in base.rows[0].signals if s.key == "blocked_ratio")
    assert round(base_blocked.score) == 30

    monkeypatch.setattr(
        analytics_service,
        "get_settings",
        lambda: Settings(RISK_MODEL=RiskModelConfig(blocked_ratio_ceil=0.80)),
    )
    tuned = await analytics_service.get_branch_risk(db_session, since, now, branch=None)
    tuned_blocked = next(s for s in tuned.rows[0].signals if s.key == "blocked_ratio")
    assert round(tuned_blocked.score) == 15
    assert tuned.rows[0].score < base.rows[0].score


async def test_branch_risk_batched_inputs_are_per_branch(db_session: AsyncSession, monkeypatch):
    """Two branches with different sensitive-category config: the batched
    per-branch queries must not bleed one branch's settings into another."""
    monkeypatch.setattr(
        analytics_service,
        "get_settings",
        lambda: Settings(
            LOG_SOURCES=[
                LogSource(branch="hq", path="/x/hq.log"),
                LogSource(branch="warehouse", path="/x/wh.log"),
            ]
        ),
    )
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    since = now - timedelta(hours=1)
    bucket = since + timedelta(minutes=1)
    db_session.add_all(
        [
            _minute(bucket_ts=bucket, branch="hq", total_requests=100, allowed_requests=100, total_bytes=10_000),
            _minute(bucket_ts=bucket, branch="warehouse", total_requests=100, allowed_requests=100, total_bytes=10_000),
            # pokerstars.com -> gambling (inferred); both branches see the same bytes
            DomainMinuteAggregate(bucket_ts=bucket, domain="pokerstars.com", branch="hq", request_count=50, total_bytes=6_000),
            DomainMinuteAggregate(bucket_ts=bucket, domain="pokerstars.com", branch="warehouse", request_count=50, total_bytes=6_000),
            # only hq marks gambling as sensitive
            AlertSettings(branch="hq", sensitive_categories="gambling"),
        ]
    )
    await db_session.commit()

    result = await analytics_service.get_branch_risk(db_session, since, now, branch=None)
    by_branch = {r.branch: r for r in result.rows}
    hq_sensitive = next(s for s in by_branch["hq"].signals if s.key == "sensitive_traffic")
    wh_sensitive = next(s for s in by_branch["warehouse"].signals if s.key == "sensitive_traffic")
    assert hq_sensitive.raw_value > 0  # hq: gambling counts, 6000/10000 = 0.6 share
    assert wh_sensitive.raw_value == 0  # warehouse: gambling not marked sensitive
