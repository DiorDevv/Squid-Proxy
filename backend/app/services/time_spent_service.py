"""Approximates how long a client spent on each domain from discrete Squid
request timestamps -- there's no continuous "session" in the log itself, so
consecutive requests to the same domain are grouped into a session as long
as the gap between them stays under SESSION_GAP_MINUTES; a longer gap (a
lunch break, the browser tab left idle) starts a new session instead of
inflating the previous one. This is a deliberate approximation, not a
precise dwell-time measurement.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain_category import DomainCategoryLabel
from app.models.raw_event import RawEvent
from app.schemas.clients import CategoryTimeSpent, DomainTimeSpent
from app.services.category_inference import effective_category
from app.services.domain_category_service import get_overrides_map


def _summarize_sessions(timestamps: list[datetime], gap: timedelta) -> tuple[int, int]:
    """`timestamps` must already be sorted ascending. Returns
    (total_seconds, session_count)."""
    if not timestamps:
        return 0, 0

    total_seconds = 0.0
    session_count = 0
    session_start = timestamps[0]
    session_end = timestamps[0]
    for ts in timestamps[1:]:
        if ts - session_end > gap:
            total_seconds += (session_end - session_start).total_seconds()
            session_count += 1
            session_start = ts
        session_end = ts
    total_seconds += (session_end - session_start).total_seconds()
    session_count += 1
    return int(total_seconds), session_count


async def get_time_spent(
    session: AsyncSession, client_ip: str, since: datetime, until: datetime
) -> list[DomainTimeSpent]:
    gap = timedelta(minutes=get_settings().SESSION_GAP_MINUTES)

    rows = (
        await session.execute(
            select(RawEvent.domain, RawEvent.timestamp)
            .where(
                RawEvent.client_ip == client_ip,
                RawEvent.timestamp >= since,
                RawEvent.timestamp <= until,
                RawEvent.domain.is_not(None),
            )
            .order_by(RawEvent.timestamp)
        )
    ).all()

    # Rows arrive ordered by timestamp already, so each per-domain bucket
    # (a subsequence of a sorted sequence) stays sorted without re-sorting.
    timestamps_by_domain: dict[str, list[datetime]] = defaultdict(list)
    for domain, timestamp in rows:
        timestamps_by_domain[domain].append(timestamp)

    items = []
    for domain, timestamps in timestamps_by_domain.items():
        total_seconds, session_count = _summarize_sessions(timestamps, gap)
        items.append(DomainTimeSpent(domain=domain, total_seconds=total_seconds, session_count=session_count))

    items.sort(key=lambda item: item.total_seconds, reverse=True)
    return items


async def get_time_spent_by_category(
    session: AsyncSession, client_ip: str, since: datetime, until: datetime
) -> list[CategoryTimeSpent]:
    """Rolls up get_time_spent()'s per-domain totals by effective category
    (admin override, else the auto-inferred guess -- see
    category_inference.effective_category) rather than re-deriving sessions
    from scratch. A "session" stays defined per-domain (see
    _summarize_sessions); this just regroups those already-computed totals,
    since a cross-domain "category session" (e.g. treating a YouTube tab
    then a Netflix tab as one continuous video-watching session) is a
    different, harder-to-justify definition this doesn't attempt."""
    domain_items = await get_time_spent(session, client_ip, since, until)
    overrides = await get_overrides_map(session)

    totals: dict[DomainCategoryLabel, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "sessions": 0})
    for item in domain_items:
        category = effective_category(item.domain, overrides)
        totals[category]["seconds"] += item.total_seconds
        totals[category]["sessions"] += item.session_count

    items = [
        CategoryTimeSpent(
            category=category,
            total_seconds=totals_for["seconds"],
            session_count=totals_for["sessions"],
        )
        for category, totals_for in totals.items()
    ]
    items.sort(key=lambda item: item.total_seconds, reverse=True)
    return items
