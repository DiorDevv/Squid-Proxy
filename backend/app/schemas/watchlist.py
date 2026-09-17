from datetime import datetime

from pydantic import BaseModel, Field

from app.models.watchlist_entry import WatchlistTargetType


class WatchlistEntryOut(BaseModel):
    id: str
    target_type: WatchlistTargetType
    value: str
    note: str | None
    # "" means "any branch"
    branch: str
    active: bool
    created_at: datetime
    last_seen_at: datetime | None
    last_alerted_at: datetime | None


class CreateWatchlistEntryRequest(BaseModel):
    target_type: WatchlistTargetType
    value: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=500)
    # "" or omitted = any branch
    branch: str = ""


class UpdateWatchlistEntryRequest(BaseModel):
    active: bool
