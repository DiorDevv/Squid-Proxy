"""Builds the subject-access dossier: everything this deployment currently
knows about one client IP or proxy-auth user, assembled from the same
aggregates the Analytics -> Who actor drill-down and the watchlist already
use -- not a new data path, a new *view* over existing ones (docs/PRODUCT.md
#4). Signed the same way exports are (app/services/export_signing.py), so
the whole JSON document can be handed to someone and checked later.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.watchlist_entry import WatchlistTargetType
from app.schemas.subject_access import SubjectDossierResponse, SubjectType, WatchlistStatus
from app.services import export_signing, squid_ops_service, watchlist_service


async def _watchlist_status(
    session: AsyncSession, subject_type: SubjectType, value: str, branch: str | None
) -> WatchlistStatus:
    target_type = WatchlistTargetType.USER if subject_type == "user" else WatchlistTargetType.CLIENT_IP
    normalized = watchlist_service.normalize_value(target_type, value)
    entries = await watchlist_service.list_entries(session, branch)
    match = next((e for e in entries if e.target_type == target_type and e.value == normalized), None)
    if match is None:
        return WatchlistStatus(watched=False)
    return WatchlistStatus(
        watched=True,
        active=match.active,
        note=match.note,
        last_seen_at=match.last_seen_at,
        last_alerted_at=match.last_alerted_at,
    )


def _manifest(response: SubjectDossierResponse) -> dict:
    """The facts a signature vouches for -- deliberately a small, stable
    summary (not the full nested activity payload) so it stays readable and
    isn't sensitive to unrelated field additions to ActorDetailResponse."""
    a = response.activity
    return {
        "subject_type": response.subject_type,
        "value": response.value,
        "branch": response.branch,
        "window_since": response.window_since.isoformat(),
        "window_until": response.window_until.isoformat(),
        "generated_at": response.generated_at.isoformat(),
        "request_count": a.request_count,
        "blocked_count": a.blocked_count,
        "total_bytes": a.total_bytes,
        "first_seen": a.first_seen.isoformat() if a.first_seen else None,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "watchlist_watched": response.watchlist.watched,
    }


async def build_dossier(
    session: AsyncSession, subject_type: SubjectType, value: str, branch: str | None
) -> SubjectDossierResponse:
    settings = get_settings()
    until = datetime.now(UTC)
    # The full window aggregates are still retained for -- not a
    # UI-selected range, since a dossier means "everything we still have",
    # and raw_events (30d default) ages out well before the aggregates
    # (400d default) do.
    since = until - timedelta(days=settings.RETENTION_DAYS_AGGREGATES)

    activity = await squid_ops_service.get_actor_detail(
        session, value, subject_type == "user", since, until, branch
    )
    watchlist = await _watchlist_status(session, subject_type, value, branch)

    response = SubjectDossierResponse(
        subject_type=subject_type,
        value=value,
        branch=branch,
        window_since=since,
        window_until=until,
        generated_at=until,
        activity=activity,
        watchlist=watchlist,
        algorithm=export_signing.ALGORITHM,
        signature=None,
        public_key=None,
    )
    signature = export_signing.sign(_manifest(response))
    if signature is not None:
        response.signature = signature
        response.public_key = export_signing.public_key_b64()
    return response
