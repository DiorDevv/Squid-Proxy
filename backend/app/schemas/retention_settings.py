from datetime import datetime

from pydantic import BaseModel, Field


class RetentionSettingsOut(BaseModel):
    raw_events_days: int
    halt_purge_if_archive_lag_days: int | None
    updated_at: datetime


class UpdateRetentionSettingsRequest(BaseModel):
    # 1..3650 -- a lower bound of 1 (not 0) so "keep nothing" isn't a
    # one-keystroke setting; the real floor for a useful deployment is
    # higher but that's the operator's call.
    raw_events_days: int = Field(ge=1, le=3650)
    # null = off. When set, the raw_events purge is skipped for a cycle
    # where archiving is more than this many days behind.
    halt_purge_if_archive_lag_days: int | None = Field(default=None, ge=1, le=365)
