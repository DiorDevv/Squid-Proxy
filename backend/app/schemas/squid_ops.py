"""Response models for the Analytics section's Squid-operational views
("Traffic & cache", "Blocks", "Who"). Backed by
app/services/squid_ops_service.py and the *_minute_aggregates tables from
migration f3b8d1c6a274 -- no new per-request scanning except the drill-down
detail, which reads raw_events for one selected actor.
"""

from datetime import datetime

from pydantic import BaseModel

from app.models.domain_category import DomainCategoryLabel
from app.schemas.analytics import TrendGranularity


class NamedCount(BaseModel):
    """Generic (label, count, bytes, %) row -- result codes, methods,
    status codes, hierarchy codes all share this shape."""

    label: str
    request_count: int
    total_bytes: int
    pct: float


class TimeBucketCounts(BaseModel):
    bucket_ts: datetime
    # label -> request count in that bucket
    values: dict[str, int]


class ResultCodeResponse(BaseModel):
    granularity: TrendGranularity
    # cache-relevant grouping over the whole window
    hit_ratio: float | None
    byte_hit_ratio: float | None
    denied_ratio: float
    tunnel_ratio: float
    codes: list[NamedCount]
    series_labels: list[str]
    series: list[TimeBucketCounts]


class HttpBreakdownResponse(BaseModel):
    methods: list[NamedCount]
    status_codes: list[NamedCount]
    status_classes: list[NamedCount]
    # called out because they are policy signals, not just error counts
    denied_403: int
    proxy_auth_407: int
    server_error_5xx: int


class HierarchyResponse(BaseModel):
    codes: list[NamedCount]


class ResponseTimePoint(BaseModel):
    bucket_ts: datetime
    p50: float
    p95: float
    p99: float
    mean: float
    request_count: int


class ResponseTimeResponse(BaseModel):
    granularity: TrendGranularity
    # over the whole window
    overall_p50: float
    overall_p95: float
    overall_p99: float
    overall_mean: float
    sample_count: int
    # histogram band counts over the whole window, in band order
    bands: list[NamedCount]
    series: list[ResponseTimePoint]


class ActorRow(BaseModel):
    """One row of the "who is doing what" leaderboard -- a proxy-auth user
    or, when the deployment has no auth, a client IP."""

    actor: str
    is_user: bool
    request_count: int
    blocked_count: int
    blocked_ratio: float
    total_bytes: int
    top_category: DomainCategoryLabel | None


class ActorLeaderboardResponse(BaseModel):
    # "user" when at least one authenticated user was seen in the window,
    # else "client_ip" -- tells the frontend which column header to show.
    actor_kind: str
    rows: list[ActorRow]
    # When actor_kind == "user" and proxy auth is only partial, this is how
    # many requests in the window had no user and so aren't represented by
    # any row above (0 for the client_ip view). The frontend surfaces it so
    # the row totals visibly don't have to reconcile with the Overview tab.
    unattributed_requests: int = 0


class ActorCategorySlice(BaseModel):
    category: DomainCategoryLabel
    request_count: int
    total_bytes: int


class ActorDomainRow(BaseModel):
    domain: str
    request_count: int
    blocked_count: int
    total_bytes: int


class ActorDetailResponse(BaseModel):
    actor: str
    is_user: bool
    first_seen: datetime | None
    last_seen: datetime | None
    request_count: int
    blocked_count: int
    total_bytes: int
    categories: list[ActorCategorySlice]
    top_domains: list[ActorDomainRow]
    denied_domains: list[ActorDomainRow]
    # 24-slot UTC hour-of-day request counts
    hourly: list[int]


class NewEntitiesResponse(BaseModel):
    since: datetime
    until: datetime
    new_users: list[str]
    new_clients: list[str]
    # how many were found before the caps above were applied
    new_users_total: int
    new_clients_total: int


class DenialReasonPoint(BaseModel):
    bucket_ts: datetime
    acl_denied: int
    proxy_auth: int
    other_blocked: int


class DenialsResponse(BaseModel):
    granularity: TrendGranularity
    total_denied: int
    acl_denied: int
    proxy_auth: int
    other_blocked: int
    series: list[DenialReasonPoint]
    top_domains: list[ActorDomainRow]
    top_categories: list[ActorCategorySlice]
    top_actors: list[ActorRow]


class BranchIngestRow(BaseModel):
    branch: str
    tailer_alive: bool
    parse_failure_rate: float | None
    lines_seen: int
    lines_parsed: int


class IngestHealthResponse(BaseModel):
    aggregator_backlog_ratio: float
    aggregator_events_likely_lost: bool
    branches: list[BranchIngestRow]
