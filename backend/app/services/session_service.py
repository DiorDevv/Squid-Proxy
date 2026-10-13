"""Sign-in sessions on top of refresh tokens.

Every login starts a session: a RefreshToken row with a fresh session_id.
Each /api/auth/refresh rotates the token but carries session_id (and the
session's start time, client details and reauth timestamp) forward, so the
one non-revoked, unexpired row per session_id *is* that session. Revoking a
session revokes its rows; api/deps._authenticate then rejects its access
tokens on the very next request.
"""

import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import Request
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_refresh_secret
from app.models.refresh_token import RefreshToken
from app.schemas.auth import SessionOut

_USER_AGENT_MAX = 255


def client_ip(request: Request) -> str | None:
    # Same address the rate limiter keys on (see app/core/rate_limit.py for
    # why that's the right one behind the reverse proxy).
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:_USER_AGENT_MAX] if value else None


def new_token(
    db: AsyncSession,
    request: Request,
    user_id: str,
    *,
    session_id: str | None = None,
    session_started_at: datetime | None = None,
    reauth_at: datetime | None = None,
) -> tuple[RefreshToken, str]:
    """Adds (uncommitted) a refresh-token row for a new session, or -- given
    session_id -- the next token of an existing one. Returns the row and
    the raw secret for the cookie."""
    jti, raw_secret, secret_hash, expires_at = generate_refresh_secret()
    now = datetime.now(UTC)
    row = RefreshToken(
        jti=jti,
        user_id=user_id,
        token_hash=secret_hash,
        expires_at=expires_at,
        session_id=session_id or str(uuid.uuid4()),
        ip=client_ip(request),
        user_agent=_user_agent(request),
        session_started_at=session_started_at or now,
        last_seen_at=now,
        reauth_at=reauth_at,
    )
    db.add(row)
    return row, raw_secret


async def list_sessions(db: AsyncSession, user_id: str) -> list[RefreshToken]:
    rows = (
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .order_by(RefreshToken.last_seen_at.desc())
        )
    ).scalars()
    return list(rows)


async def count_sessions(db: AsyncSession, user_id: str) -> int:
    return len(await list_sessions(db, user_id))


async def revoke(
    db: AsyncSession,
    user_id: str,
    *,
    session_id: str | None = None,
    keep_session_id: str | None = None,
) -> int:
    """Revokes one session of `user_id` (session_id given) or all of them,
    optionally sparing `keep_session_id`. Doesn't commit. Returns how many
    live sessions were closed."""
    query = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
    if session_id is not None:
        query = query.where(RefreshToken.session_id == session_id)
    if keep_session_id is not None:
        query = query.where(RefreshToken.session_id != keep_session_id)
    live = query.where(RefreshToken.expires_at > datetime.now(UTC)).values(revoked=True)
    closed = cast(CursorResult, await db.execute(live)).rowcount
    # Already-expired leftovers too, so nothing of the session is reusable.
    await db.execute(query.values(revoked=True))
    return closed


async def mark_reauth(db: AsyncSession, session_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.revoked.is_(False))
        .values(reauth_at=datetime.now(UTC))
    )


def to_out(row: RefreshToken, current_session_id: str | None) -> SessionOut:
    return SessionOut(
        id=row.session_id,
        ip=row.ip,
        user_agent=row.user_agent,
        started_at=row.session_started_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        current=row.session_id == current_session_id,
    )
