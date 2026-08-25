from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import DEFAULT_BRANCH, get_settings
from app.models.alert_settings import AlertSettings
from app.models.telegram_link_code import TelegramLinkCode, TelegramLinkTarget
from app.schemas.alerts import (
    AlertSettingsOut,
    TelegramLinkCodeOut,
    TelegramLinkStatusOut,
    TelegramSuperAdminOut,
    UpdateAlertSettingsRequest,
)
from app.services import (
    alert_settings_service,
    telegram_alerting,
    telegram_global_settings_service,
    telegram_link_service,
)

router = APIRouter(
    prefix="/api/alert-settings", tags=["alert-settings"], dependencies=[Depends(require_admin)]
)


async def _scoped_branch(
    branch: str = Query(default=DEFAULT_BRANCH),
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    """Same substitution/rejection contract as api.deps.resolve_branch, but
    with DEFAULT_BRANCH (not None/"all") as the concrete fallback these
    single-branch settings need: a branch-scoped admin is pinned to their
    own branch, silently if they didn't ask for a specific one, 403 if they
    explicitly asked for a different one -- previously unchecked, letting
    any branch-scoped admin read or overwrite another branch's alert
    thresholds."""
    if current_user.branch is not None and branch != DEFAULT_BRANCH and branch != current_user.branch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this branch."
        )
    return current_user.branch or branch


async def _require_unrestricted_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """The super-admin Telegram chat is global, not scoped to any one
    branch -- only an unrestricted admin (current_user.branch is None) may
    view or (re-)link it. A branch-scoped admin has no legitimate reason to
    reach these endpoints at all, so this rejects outright rather than
    substituting/redirecting the way _scoped_branch does."""
    if current_user.branch is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an unrestricted admin can manage the super-admin Telegram chat.",
        )
    return current_user


def _link_code_to_out(row: TelegramLinkCode) -> TelegramLinkCodeOut:
    return TelegramLinkCodeOut(code=row.code, expires_at=row.expires_at)


def _to_out(row: AlertSettings) -> AlertSettingsOut:
    return AlertSettingsOut(
        branch=row.branch,
        sensitive_categories=sorted(
            alert_settings_service.parse_sensitive_categories(row.sensitive_categories), key=lambda c: c.value
        ),
        non_work_minutes_threshold=row.non_work_minutes_threshold,
        client_daily_byte_quota_bytes=row.client_daily_byte_quota_bytes,
        uncategorized_domain_request_threshold=row.uncategorized_domain_request_threshold,
        telegram_chat_id=row.telegram_chat_id,
        updated_at=row.updated_at,
    )


@router.get("", response_model=AlertSettingsOut)
async def read_alert_settings(
    branch: str = Depends(_scoped_branch), db: AsyncSession = Depends(get_db)
) -> AlertSettingsOut:
    row = await alert_settings_service.get_settings_row(db, branch)
    return _to_out(row)


@router.put("", response_model=AlertSettingsOut)
async def update_alert_settings(
    body: UpdateAlertSettingsRequest,
    branch: str = Depends(_scoped_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AlertSettingsOut:
    row = await alert_settings_service.update_settings(
        db,
        sensitive_categories=body.sensitive_categories,
        non_work_minutes_threshold=body.non_work_minutes_threshold,
        client_daily_byte_quota_bytes=body.client_daily_byte_quota_bytes,
        actor_user_id=current_user.user_id,
        uncategorized_domain_request_threshold=body.uncategorized_domain_request_threshold,
        telegram_chat_id=body.telegram_chat_id,
        branch=branch,
    )
    return _to_out(row)


class TestTelegramAlertRequest(BaseModel):
    telegram_chat_id: str


@router.post("/test-telegram", status_code=status.HTTP_204_NO_CONTENT)
async def test_telegram_alert(
    body: TestTelegramAlertRequest,
    branch: str = Depends(_scoped_branch),
) -> None:
    """Sends a one-off test message to the given chat id, independent of
    what's saved -- lets an admin verify a chat id before persisting it."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram bot token is not configured on the server.",
        )
    try:
        await telegram_alerting.send_message(
            settings.TELEGRAM_BOT_TOKEN,
            body.telegram_chat_id,
            f'Squid: test message for branch "{branch}" -- Telegram alerts are wired up correctly.',
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send the Telegram test message. Check the chat ID and that the bot "
            "has been added to that chat.",
        ) from exc


@router.post("/telegram-link", response_model=TelegramLinkCodeOut)
async def create_telegram_link_code(
    branch: str = Depends(_scoped_branch),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TelegramLinkCodeOut:
    """Issues a fresh 6-digit pairing code for `branch` -- see
    app/services/telegram_link_service.py. Shown in the dashboard; redeemed
    by sending it to the bot in Telegram (app/services/telegram_link_poller.py)."""
    row = await telegram_link_service.create_branch_code(db, branch, current_user.user_id)
    return _link_code_to_out(row)


@router.post("/telegram-link/super-admin", response_model=TelegramLinkCodeOut)
async def create_super_admin_telegram_link_code(
    current_user: CurrentUser = Depends(_require_unrestricted_admin),
    db: AsyncSession = Depends(get_db),
) -> TelegramLinkCodeOut:
    row = await telegram_link_service.create_super_admin_code(db, current_user.user_id)
    return _link_code_to_out(row)


@router.get("/telegram-link/{code}/status", response_model=TelegramLinkStatusOut)
async def get_telegram_link_status(
    code: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TelegramLinkStatusOut:
    """Re-applies the same scoping a code's creation endpoint would have
    enforced, keyed off the code's own stored target/branch -- a
    branch-scoped admin can't poll another branch's (or the super-admin's)
    pending code just by guessing/knowing its 6 digits."""
    row = await telegram_link_service.get_code(db, code)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found.")

    if row.target == TelegramLinkTarget.SUPER_ADMIN:
        if current_user.branch is not None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    elif current_user.branch is not None and row.branch != current_user.branch:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")

    return TelegramLinkStatusOut(
        consumed=row.consumed_at is not None,
        expired=row.consumed_at is None and row.expires_at < datetime.now(UTC),
        chat_id=row.consumed_chat_id,
    )


@router.get("/telegram-super-admin", response_model=TelegramSuperAdminOut)
async def get_super_admin_telegram(
    current_user: CurrentUser = Depends(_require_unrestricted_admin),
    db: AsyncSession = Depends(get_db),
) -> TelegramSuperAdminOut:
    row = await telegram_global_settings_service.get_settings_row(db)
    return TelegramSuperAdminOut(chat_id=row.super_admin_chat_id)
