"""Issues and redeems the 6-digit Telegram pairing codes shown in the
dashboard (see app/models/telegram_link_code.py). A code is redeemed by
sending it to the bot in Telegram -- app/services/telegram_link_poller.py
watches for that and calls consume_code() below.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram_link_code import TelegramLinkCode, TelegramLinkTarget
from app.services import alert_settings_service, telegram_global_settings_service

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10
# Vanishingly unlikely to ever be needed (1,000,000 possible codes, and in
# practice at most a handful of pending codes at once) -- just a safety
# bound against an infinite loop, not a real capacity limit.
_MAX_GENERATION_ATTEMPTS = 20


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


async def _code_is_pending(session: AsyncSession, code: str) -> bool:
    """True if `code` currently matches an active (unconsumed, unexpired)
    row for *any* target/branch -- the poller matches purely on the code
    string, so two simultaneously-active codes must never collide,
    regardless of which branch (or the super-admin) each belongs to."""
    row = (
        await session.execute(
            select(TelegramLinkCode.id).where(
                TelegramLinkCode.code == code,
                TelegramLinkCode.consumed_at.is_(None),
                TelegramLinkCode.expires_at > datetime.now(UTC),
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def _unique_code(session: AsyncSession) -> str:
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_code()
        if not await _code_is_pending(session, code):
            return code
    raise RuntimeError("Could not generate a unique Telegram link code -- too many pending codes.")


async def _expire_pending(session: AsyncSession, target: TelegramLinkTarget, branch: str | None) -> None:
    """Invalidates any other still-pending code for the same target (same
    branch, or the super-admin) -- only the newest code for a given target
    ever works, so an admin who re-clicks "Connect" can't be confused by an
    earlier code still silently being valid."""
    now = datetime.now(UTC)
    pending = (
        await session.execute(
            select(TelegramLinkCode).where(
                TelegramLinkCode.target == target,
                TelegramLinkCode.branch == branch,
                TelegramLinkCode.consumed_at.is_(None),
                TelegramLinkCode.expires_at > now,
            )
        )
    ).scalars().all()
    for row in pending:
        row.expires_at = now


async def create_branch_code(session: AsyncSession, branch: str, actor_user_id: str) -> TelegramLinkCode:
    await _expire_pending(session, TelegramLinkTarget.BRANCH, branch)
    now = datetime.now(UTC)
    row = TelegramLinkCode(
        code=await _unique_code(session),
        target=TelegramLinkTarget.BRANCH,
        branch=branch,
        created_by_user_id=actor_user_id,
        created_at=now,
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_super_admin_code(session: AsyncSession, actor_user_id: str) -> TelegramLinkCode:
    await _expire_pending(session, TelegramLinkTarget.SUPER_ADMIN, None)
    now = datetime.now(UTC)
    row = TelegramLinkCode(
        code=await _unique_code(session),
        target=TelegramLinkTarget.SUPER_ADMIN,
        branch=None,
        created_by_user_id=actor_user_id,
        created_at=now,
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_code(session: AsyncSession, code: str) -> TelegramLinkCode | None:
    """For the status-check endpoint -- the newest row matching `code`,
    consumed or not, expired or not (the caller decides what to report)."""
    return (
        await session.execute(
            select(TelegramLinkCode)
            .where(TelegramLinkCode.code == code)
            .order_by(TelegramLinkCode.created_at.desc())
        )
    ).scalars().first()


async def consume_code(session: AsyncSession, code: str, chat_id: str) -> TelegramLinkCode | None:
    """Redeems `code` (as sent to the bot from `chat_id`) if it matches a
    still-pending row, writing `chat_id` to the target it was issued for
    and marking the row consumed -- all in one commit, so a code is never
    left half-redeemed. Returns None (nothing committed) if no pending code
    matches, so the poller can reply "invalid/expired" instead."""
    row = (
        await session.execute(
            select(TelegramLinkCode)
            .where(
                TelegramLinkCode.code == code,
                TelegramLinkCode.consumed_at.is_(None),
                TelegramLinkCode.expires_at > datetime.now(UTC),
            )
            .order_by(TelegramLinkCode.created_at.desc())
        )
    ).scalars().first()
    if row is None:
        return None

    if row.target == TelegramLinkTarget.BRANCH:
        assert row.branch is not None
        await alert_settings_service.set_telegram_chat_id(
            session, row.branch, chat_id, row.created_by_user_id
        )
    else:
        await telegram_global_settings_service.set_super_admin_chat_id(
            session, chat_id, row.created_by_user_id
        )

    row.consumed_at = datetime.now(UTC)
    row.consumed_chat_id = chat_id
    await session.commit()
    await session.refresh(row)
    return row
