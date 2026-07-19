from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import RangeParam


class SummaryResponse(BaseModel):
    # `range` is only set when the request used a preset (1h/24h/7d); a
    # custom from_ts/to_ts window leaves it null and relies on since/until
    # instead (see app/schemas/common.py:EffectiveRange).
    range: RangeParam | None
    since: datetime
    until: datetime
    total_requests: int
    blocked_requests: int
    allowed_requests: int
    active_client_count: int
    active_user_count: int
