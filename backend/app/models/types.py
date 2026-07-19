"""Shared column types.

SQLite (and some drivers even on Postgres round-trips) silently drops
tzinfo on a `DateTime(timezone=True)` column: the value written was UTC,
but what comes back out of a `SELECT` is a *naive* datetime. Pydantic then
serializes that naive datetime to JSON without a `Z`/`+00:00` suffix, and
every browser's `new Date(...)` parses a timezone-less date-time string as
*local* time -- so a client's `last_activity` from moments ago rendered as
"5h ago" for a viewer 5 hours ahead of UTC. `UTCDateTime` closes that gap
at the ORM boundary, once, instead of requiring every route/service to
remember to re-attach `tzinfo=UTC` by hand.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
