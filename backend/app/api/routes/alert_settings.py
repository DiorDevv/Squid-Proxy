from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import DEFAULT_BRANCH, get_settings
from app.models.alert_settings import AlertSettings
from app.schemas.alerts import AlertSettingsOut, UpdateAlertSettingsRequest
from app.services import alert_settings_service, telegram_alerting

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
