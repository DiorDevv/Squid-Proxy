from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import Granularity


class TimeseriesPoint(BaseModel):
    bucket_ts: datetime
    total_requests: int
    blocked_requests: int
    allowed_requests: int


class TimeseriesResponse(BaseModel):
    granularity: Granularity
    points: list[TimeseriesPoint]
