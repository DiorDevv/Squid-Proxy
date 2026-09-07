from pydantic import BaseModel


class CollectedField(BaseModel):
    name: str
    description: str


class RetentionWindows(BaseModel):
    raw_events_days: int
    aggregates_days: int
    ops_aggregates_days: int
    archives_days: int
    client_minute_rollup_after_hours: int


class ArchivingPolicy(BaseModel):
    enabled: bool
    encrypted: bool
    output_dir: str


class DataPolicyResponse(BaseModel):
    """A plain-language statement of what this deployment records about
    people's proxy use, why, and for how long -- read-only, assembled from
    the settings already in effect. Not a substitute for a real privacy
    notice, but the factual basis one is written from."""

    purpose: str | None
    controller: str | None
    retention: RetentionWindows
    archiving: ArchivingPolicy
    collected_fields: list[CollectedField]
