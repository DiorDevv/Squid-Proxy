"""Records and reads back audit-log entries -- admin actions (see
app/services/user_service.py etc. for the write side) and read-access
entries (who viewed whose activity, who ran which search)."""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.user import User
from app.schemas.audit import AuditLogEntryOut
from app.schemas.common import Page

logger = logging.getLogger(__name__)

# Field separator for the canonical serialization below -- ASCII record
# separator, which can't occur in any of the fields it joins (emails, UUIDs,
# enum values, free-text detail is the only wildcard and even there it's not
# a character anything produces).
_HASH_SEP = "\x1e"
_NULL_SENTINEL = "\x00"  # so None and "" hash differently


def _canonical(value: object) -> str:
    return _NULL_SENTINEL if value is None else str(value)


def compute_entry_hash(
    *,
    prev_hash: str | None,
    entry_id: str,
    created_at: datetime,
    action: AuditAction | str,
    branch: str | None,
    actor_user_id: str,
    actor_email: str,
    target_user_id: str | None,
    target_email: str | None,
    detail: str | None,
) -> str:
    """SHA-256 of (previous entry's hash) + (this row's immutable fields).
    One implementation shared by record() (write side), verify_chain()
    (read side) and the migration that backfills existing rows -- they must
    agree byte-for-byte or the chain appears broken at their boundary.
    created_at is normalized to a UTC microsecond ISO string so a value
    that round-trips through SQLite (str) or Postgres (aware datetime)
    hashes identically either way."""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    ts = created_at.astimezone(UTC).isoformat(timespec="microseconds")
    action_value = action.value if isinstance(action, AuditAction) else str(action)
    payload = _HASH_SEP.join(
        [
            _canonical(prev_hash),
            _canonical(entry_id),
            ts,
            action_value,
            _canonical(branch),
            _canonical(actor_user_id),
            _canonical(actor_email),
            _canonical(target_user_id),
            _canonical(target_email),
            _canonical(detail),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _latest_entry_hash(session: AsyncSession) -> str | None:
    """The entry_hash the next row must chain onto -- the most recent entry
    by (created_at, id). Autoflush means a row add()ed earlier in this same
    session (a request making two audited changes) is already visible here,
    so those chain correctly; only writes racing in *separate* transactions
    can fork, which verify_chain reports rather than hides."""
    return (
        await session.execute(
            select(AuditLogEntry.entry_hash)
            .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# Read-access views are often driven by paging or a polling fallback that
# re-issues the same query -- collapse an identical (actor, action, detail)
# within this window into one entry so the log stays "who looked at whom",
# not a request trace.
_READ_ACCESS_DEDUP_WINDOW = timedelta(minutes=5)


async def _resolve_actor_email(session: AsyncSession, actor_user_id: str) -> str:
    email = (await session.execute(select(User.email).where(User.id == actor_user_id))).scalar_one_or_none()
    return email or "unknown"


async def record(
    session: AsyncSession,
    *,
    action: AuditAction,
    actor_user_id: str,
    branch: str | None = None,
    target_user_id: str | None = None,
    target_email: str | None = None,
    detail: str | None = None,
) -> None:
    """Adds an audit row to `session` without committing -- callers add this
    to the same transaction as the change it describes, so the two can
    never disagree (an audited action that didn't happen, or vice versa).

    `branch` tags which branch this action is scoped to, mirroring whatever
    branch value the caller already resolved for the change itself (e.g. the
    target user's branch, the export job's branch). Leave it unset (None)
    only for actions with no branch dimension or with unrestricted reach --
    see AuditLogEntry.branch and list_entries for how that's read back."""
    actor_email = await _resolve_actor_email(session, actor_user_id)
    # Generate id/created_at here rather than leaning on the column defaults
    # so the exact values that go into the hash are known before flush.
    entry_id = str(uuid.uuid4())
    created_at = datetime.now(UTC)
    prev_hash = await _latest_entry_hash(session)
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        entry_id=entry_id,
        created_at=created_at,
        action=action,
        branch=branch,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        target_user_id=target_user_id,
        target_email=target_email,
        detail=detail,
    )
    session.add(
        AuditLogEntry(
            id=entry_id,
            created_at=created_at,
            action=action,
            branch=branch,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_user_id=target_user_id,
            target_email=target_email,
            detail=detail,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
    )


_READ_ACCESS_ACTIONS = frozenset(
    {
        AuditAction.CLIENT_ACTIVITY_VIEWED,
        AuditAction.EVENT_SEARCH_RUN,
        AuditAction.ANALYTICS_ACTOR_VIEWED,
        AuditAction.SUBJECT_DOSSIER_EXPORTED,
    }
)


async def record_read_access(
    session: AsyncSession,
    *,
    action: AuditAction,
    actor_user_id: str,
    branch: str | None = None,
    detail: str,
) -> None:
    """Record (and commit on its own) that `actor_user_id` viewed something.

    Unlike record(), a read has no surrounding change transaction to ride
    along with, so this commits itself. It's best-effort: a failure to log
    the access is logged as a WARNING but never propagated -- denying a
    compliance reviewer their data because the audit INSERT hiccuped is the
    worse failure. An identical entry within _READ_ACCESS_DEDUP_WINDOW is
    skipped (paging / polling re-issues the same query).
    """
    assert action in _READ_ACCESS_ACTIONS, action
    try:
        since = datetime.now(UTC) - _READ_ACCESS_DEDUP_WINDOW
        recent = await session.execute(
            select(AuditLogEntry.id)
            .where(
                and_(
                    AuditLogEntry.action == action,
                    AuditLogEntry.actor_user_id == actor_user_id,
                    AuditLogEntry.detail == detail,
                    AuditLogEntry.created_at >= since,
                )
            )
            .limit(1)
        )
        if recent.scalar_one_or_none() is not None:
            return
        await record(session, action=action, actor_user_id=actor_user_id, branch=branch, detail=detail)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("Failed to record read-access audit entry (%s)", action.value, exc_info=True)


async def list_entries(
    session: AsyncSession, limit: int, offset: int, branch: str | None = None
) -> Page[AuditLogEntryOut]:
    """`branch` follows the same contract as api.deps.resolve_branch: None
    (an unrestricted caller, or no branch requested) returns every entry.
    A concrete branch returns that branch's entries *plus* every entry with
    no branch of its own (see AuditLogEntry.branch) -- an action that wasn't
    confined to one branch is visible to everyone, only branch-confined
    entries for another branch are held back. Route callers must resolve
    `branch` through api.deps.resolve_branch first so a branch-scoped admin
    can never pass an arbitrary value here."""
    query = select(AuditLogEntry)
    count_query = select(func.count()).select_from(AuditLogEntry)
    if branch is not None:
        scope = or_(AuditLogEntry.branch.is_(None), AuditLogEntry.branch == branch)
        query = query.where(scope)
        count_query = count_query.where(scope)

    query = query.order_by(AuditLogEntry.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(query)).scalars().all()
    total = (await session.execute(count_query)).scalar_one()

    items = [
        AuditLogEntryOut(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            branch=row.branch,
            actor_email=row.actor_email,
            target_email=row.target_email,
            detail=row.detail,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


class ChainVerification:
    """Result of walking the audit-log hash chain. `ok` is True only if
    every entry's stored entry_hash recomputes exactly and links to its
    predecessor. `broken_at` (when not ok) is the first entry that failed,
    with why -- a mismatching recomputed hash means that row's fields were
    altered; a prev_hash that doesn't match the real predecessor means a row
    was inserted or deleted around it."""

    def __init__(self, ok: bool, entries_checked: int, broken_at: dict | None = None) -> None:
        self.ok = ok
        self.entries_checked = entries_checked
        self.broken_at = broken_at


async def verify_chain(session: AsyncSession) -> ChainVerification:
    """Recompute the whole chain in write order. O(n) over the audit log --
    it's an admin/auditor-triggered integrity check, not a hot path."""
    rows = (
        (
            await session.execute(
                select(AuditLogEntry).order_by(AuditLogEntry.created_at.asc(), AuditLogEntry.id.asc())
            )
        )
        .scalars()
        .all()
    )

    expected_prev: str | None = None
    for index, row in enumerate(rows):
        if row.prev_hash != expected_prev:
            return ChainVerification(
                ok=False,
                entries_checked=index,
                broken_at={
                    "id": row.id,
                    "position": index,
                    "created_at": row.created_at.isoformat(),
                    "reason": "prev_hash does not match the preceding entry "
                    "(a row was inserted or deleted here)",
                },
            )
        recomputed = compute_entry_hash(
            prev_hash=row.prev_hash,
            entry_id=row.id,
            created_at=row.created_at,
            action=row.action,
            branch=row.branch,
            actor_user_id=row.actor_user_id,
            actor_email=row.actor_email,
            target_user_id=row.target_user_id,
            target_email=row.target_email,
            detail=row.detail,
        )
        if recomputed != row.entry_hash:
            return ChainVerification(
                ok=False,
                entries_checked=index,
                broken_at={
                    "id": row.id,
                    "position": index,
                    "created_at": row.created_at.isoformat(),
                    "reason": "entry_hash does not recompute (this row's fields were altered)",
                },
            )
        expected_prev = row.entry_hash

    return ChainVerification(ok=True, entries_checked=len(rows))
