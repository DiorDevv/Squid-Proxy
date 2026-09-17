from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.squid_ops import ActorDetailResponse

SubjectType = Literal["client_ip", "user"]


class WatchlistStatus(BaseModel):
    watched: bool
    active: bool | None = None
    note: str | None = None
    last_seen_at: datetime | None = None
    last_alerted_at: datetime | None = None


class SubjectDossierResponse(BaseModel):
    """Everything this deployment currently knows about one client IP or
    proxy-auth user, in a single signed document (docs/PRODUCT.md #4:
    subject access). `activity` covers whatever of RETENTION_DAYS_AGGREGATES
    is still retained -- window_since/window_until state exactly what that
    window was at generation time, since it isn't a fixed calendar range.
    """

    subject_type: SubjectType
    value: str
    branch: str | None
    window_since: datetime
    window_until: datetime
    generated_at: datetime
    activity: ActorDetailResponse
    watchlist: WatchlistStatus
    algorithm: str
    signature: str | None
    public_key: str | None
