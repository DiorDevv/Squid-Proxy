"""Response models for the Analytics section (`/api/analytics/*`).

Everything here is computed on the fly from data that already exists
(`minute_aggregates`, `domain_minute_aggregates`, `anomaly_events`,
`alert_settings`) -- there is no analytics-specific table. See
`app/services/analytics_service.py`.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel

from app.models.domain_category import DomainCategoryLabel

RiskSignalKey: TypeAlias = Literal[
    "blocked_ratio",
    "sensitive_traffic",
    "anomalies",
    "quota_breaches",
    "uncategorized_domains",
]


class TrendGranularity(str, Enum):
    HOUR = "hour"
    DAY = "day"


class TrendMetric(str, Enum):
    BYTES = "bytes"
    REQUESTS = "requests"


class MetricDelta(BaseModel):
    """One headline number for the selected range next to the same number
    for the immediately preceding, equal-length range."""

    metric: str
    current: float
    previous: float | None
    # (current - previous) / previous * 100, or null when previous is 0 or
    # missing -- matches the frontend's getPercentChange contract so a
    # ratio can't render as Infinity/NaN.
    pct_change: float | None


class CategoryUsage(BaseModel):
    category: DomainCategoryLabel
    request_count: int
    blocked_count: int
    total_bytes: int


class DomainUsage(BaseModel):
    domain: str
    request_count: int
    blocked_count: int
    total_bytes: int
    category: DomainCategoryLabel


class CategoryMover(BaseModel):
    """A category whose traffic changed the most (by absolute byte volume)
    between the selected range and the equal-length range before it."""

    category: DomainCategoryLabel
    current_bytes: int
    previous_bytes: int
    pct_change: float | None


class AnalyticsOverview(BaseModel):
    since: datetime
    until: datetime
    previous_since: datetime
    previous_until: datetime
    metrics: list[MetricDelta]
    blocked_ratio: float
    cache_hit_ratio: float | None
    top_categories: list[CategoryUsage]
    top_domains: list[DomainUsage]
    top_blocked_domains: list[DomainUsage]
    top_movers: list[CategoryMover]


class CategoryTrendPoint(BaseModel):
    bucket_ts: datetime
    # category value -> metric value for that bucket. Only categories with a
    # non-zero value in the bucket are present; the frontend zero-fills
    # against `categories` for stacking.
    values: dict[str, int]


class CategoryTrendResponse(BaseModel):
    granularity: TrendGranularity
    metric: TrendMetric
    # Stacking/legend order: highest total over the whole window first.
    categories: list[DomainCategoryLabel]
    points: list[CategoryTrendPoint]


class BranchBreakdownRow(BaseModel):
    branch: str
    total_requests: int
    blocked_requests: int
    allowed_requests: int
    total_bytes: int
    blocked_ratio: float
    active_client_count: int
    requests_pct_change: float | None


class BranchBreakdownResponse(BaseModel):
    rows: list[BranchBreakdownRow]


class RiskSignal(BaseModel):
    """One weighted input to a branch's composite risk score. `score` is
    this signal's own contribution to the 0-100 composite (already
    normalized and multiplied by `weight`), so the frontend can stack the
    signals and have them sum to `BranchRiskRow.score`."""

    key: RiskSignalKey
    raw_value: float
    score: float
    weight: float


class BranchRiskRow(BaseModel):
    branch: str
    score: float
    band: Literal["low", "medium", "high"]
    signals: list[RiskSignal]
    total_requests: int
    blocked_requests: int
    anomaly_count: int


class BranchRiskResponse(BaseModel):
    since: datetime
    until: datetime
    rows: list[BranchRiskRow]


class HeatmapCell(BaseModel):
    # 0 = Monday .. 6 = Sunday. In the timezone implied by
    # ActivityHeatmapResponse.tz_offset_minutes (0 = UTC).
    weekday: int
    hour: int
    value: int


class ActivityHeatmapResponse(BaseModel):
    blocked_only: bool
    # Minutes east of UTC the weekday/hour split was computed in -- 0 means
    # the cells are in UTC, 300 means UTC+5, etc. Echoes the request so the
    # client can label the axes correctly.
    tz_offset_minutes: int
    max_value: int
    cells: list[HeatmapCell]


class RetentionInfo(BaseModel):
    """How far back each tier of data goes, so the UI can warn when a
    custom range reaches past what a given view actually has."""

    raw_event_days: int
    aggregate_days: int
    # The per-minute operational aggregates behind Traffic & cache / Blocks
    # -- kept a shorter time than the core aggregates.
    ops_aggregate_days: int
