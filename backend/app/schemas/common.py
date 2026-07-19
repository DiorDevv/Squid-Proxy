from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Annotated, Generic, Literal, TypeVar

from fastapi import HTTPException, Query, status
from pydantic import BaseModel

T = TypeVar("T")


class RangeParam(str, Enum):
    ONE_HOUR = "1h"
    TWENTY_FOUR_HOURS = "24h"
    SEVEN_DAYS = "7d"

    def to_timedelta(self) -> timedelta:
        return {
            RangeParam.ONE_HOUR: timedelta(hours=1),
            RangeParam.TWENTY_FOUR_HOURS: timedelta(hours=24),
            RangeParam.SEVEN_DAYS: timedelta(days=7),
        }[self]

    def since(self) -> datetime:
        return datetime.now(UTC) - self.to_timedelta()


class EffectiveRange(BaseModel):
    """The actual [since, until) window a request resolved to -- either one
    of the `RangeParam` presets (until is always "now") or an explicit
    `from_ts`/`to_ts` pair (see `resolve_range`). `range` is only set for the
    preset case, so callers/responses can still echo which preset was used
    without pretending a custom window matches one."""

    since: datetime
    until: datetime
    range: RangeParam | None = None


def _ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def resolve_range(
    range: RangeParam | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, description="Custom range start (ISO 8601)."),
    to_ts: datetime | None = Query(default=None, description="Custom range end (ISO 8601)."),
) -> EffectiveRange:
    """Shared range resolution for every range-based endpoint: either an
    explicit `from_ts`/`to_ts` pair, or a `RangeParam` preset (defaulting to
    24h) measured up to "now". Kept as one dependency so every endpoint
    validates and interprets custom ranges identically."""
    if from_ts or to_ts:
        if not (from_ts and to_ts):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from_ts and to_ts must both be provided together.",
            )
        since, until = _ensure_utc(from_ts), _ensure_utc(to_ts)
        if since >= until:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from_ts must be before to_ts.",
            )
        return EffectiveRange(since=since, until=until, range=None)

    effective = range or RangeParam.TWENTY_FOUR_HOURS
    return EffectiveRange(since=effective.since(), until=datetime.now(UTC), range=effective)


class Granularity(str, Enum):
    MINUTE = "minute"
    HOUR = "hour"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    limit: Annotated[int, Query(ge=1, le=1000)] = 50
    offset: Annotated[int, Query(ge=0)] = 0


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


SortableField = Literal[
    "client_ip", "user", "total_requests", "blocked_requests", "total_bytes", "last_activity"
]
