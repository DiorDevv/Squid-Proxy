"""Admin-tunable alerting thresholds (see app/models/alert_settings.py):
which domain categories count as "sensitive", how many non-work minutes a
day is too many, and a per-client daily byte quota. Consumed by
app/insights/anomaly.py, app/services/category_usage_monitor.py, and
app/services/quota_monitor.py.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_BRANCH
from app.models.alert_settings import AlertSettings
from app.models.audit_log import AuditAction
from app.models.domain_category import DomainCategoryLabel
from app.services import audit_service

DEFAULT_NON_WORK_MINUTES_THRESHOLD = 120


async def get_settings_row(session: AsyncSession, branch: str = DEFAULT_BRANCH) -> AlertSettings:
    """Read-only: returns the persisted row for `branch`, or an unsaved,
    in-memory default if that branch hasn't been configured yet -- a fresh
    install/new branch shouldn't need a row inserted just to be read from,
    only the first PUT actually creates one (see update_settings).
    `updated_at` is set explicitly here since the column's `default=` only
    applies at INSERT time, not on plain construction of a transient
    object."""
    row = (
        await session.execute(select(AlertSettings).where(AlertSettings.branch == branch))
    ).scalar_one_or_none()
    if row is None:
        row = AlertSettings(
            branch=branch,
            sensitive_categories="",
            non_work_minutes_threshold=DEFAULT_NON_WORK_MINUTES_THRESHOLD,
            client_daily_byte_quota_bytes=None,
            uncategorized_domain_request_threshold=None,
            telegram_chat_id=None,
            updated_at=datetime.now(UTC),
        )
    return row


def parse_sensitive_categories(raw: str) -> set[DomainCategoryLabel]:
    if not raw.strip():
        return set()
    labels: set[DomainCategoryLabel] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            labels.add(DomainCategoryLabel(token))
        except ValueError:
            continue
    return labels


async def update_settings(
    session: AsyncSession,
    sensitive_categories: list[DomainCategoryLabel],
    non_work_minutes_threshold: int,
    client_daily_byte_quota_bytes: int | None,
    actor_user_id: str,
    uncategorized_domain_request_threshold: int | None = None,
    telegram_chat_id: str | None = None,
    branch: str = DEFAULT_BRANCH,
) -> AlertSettings:
    row = (
        await session.execute(select(AlertSettings).where(AlertSettings.branch == branch))
    ).scalar_one_or_none()
    if row is None:
        row = AlertSettings(branch=branch)
        session.add(row)

    row.sensitive_categories = ",".join(category.value for category in sensitive_categories)
    row.non_work_minutes_threshold = non_work_minutes_threshold
    row.client_daily_byte_quota_bytes = client_daily_byte_quota_bytes
    row.uncategorized_domain_request_threshold = uncategorized_domain_request_threshold
    row.telegram_chat_id = telegram_chat_id
    await audit_service.record(
        session,
        action=AuditAction.ALERT_SETTINGS_UPDATED,
        actor_user_id=actor_user_id,
        branch=branch,
        detail=f"branch={branch}",
    )
    await session.commit()
    await session.refresh(row)
    return row


async def set_telegram_chat_id(
    session: AsyncSession, branch: str, chat_id: str, actor_user_id: str
) -> AlertSettings:
    """Sets only telegram_chat_id, unlike update_settings above -- used by
    telegram_link_service.consume_code, which must not require (and
    therefore risk silently resetting) the other threshold fields just to
    record a pairing-code link. Does not commit -- the caller commits once
    alongside its own TelegramLinkCode row update, so a code is never
    marked consumed without the chat id it resolved to actually being
    saved, or vice versa."""
    row = (
        await session.execute(select(AlertSettings).where(AlertSettings.branch == branch))
    ).scalar_one_or_none()
    if row is None:
        row = AlertSettings(branch=branch)
        session.add(row)

    row.telegram_chat_id = chat_id
    await audit_service.record(
        session,
        action=AuditAction.TELEGRAM_LINKED,
        actor_user_id=actor_user_id,
        branch=branch,
        detail=f"branch={branch} Telegram chat linked via pairing code",
    )
    return row
