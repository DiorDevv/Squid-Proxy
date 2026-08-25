"""Tests for the Telegram pairing-code service
(app/services/telegram_link_service.py): issuing a 6-digit code for a
branch or the super-admin target, invalidating a target's previous pending
code, and redeeming a code into an actual chat id link."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.alert_settings import AlertSettings
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.telegram_global_settings import TelegramGlobalSettings
from app.models.telegram_link_code import TelegramLinkTarget
from app.services import telegram_link_service


async def test_create_branch_code_is_six_digits_with_ten_minute_expiry(db_session):
    before = datetime.now(UTC)
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")

    assert len(row.code) == telegram_link_service.CODE_LENGTH
    assert row.code.isdigit()
    assert row.target == TelegramLinkTarget.BRANCH
    assert row.branch == "filiallar"
    assert row.consumed_at is None
    expected_expiry = before + timedelta(minutes=telegram_link_service.CODE_TTL_MINUTES)
    assert abs((row.expires_at - expected_expiry).total_seconds()) < 5


async def test_create_branch_code_invalidates_previous_pending_code_same_branch(db_session):
    first = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")

    await db_session.refresh(first)
    assert first.expires_at <= datetime.now(UTC)


async def test_create_branch_code_does_not_invalidate_other_branch_or_super_admin(db_session):
    other_branch = await telegram_link_service.create_branch_code(db_session, "other-branch", "actor-1")
    super_admin = await telegram_link_service.create_super_admin_code(db_session, "actor-1")

    await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")

    await db_session.refresh(other_branch)
    await db_session.refresh(super_admin)
    assert other_branch.expires_at > datetime.now(UTC)
    assert super_admin.expires_at > datetime.now(UTC)


async def test_consume_code_links_branch_chat_and_marks_consumed(db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")

    consumed = await telegram_link_service.consume_code(db_session, row.code, "555")

    assert consumed is not None
    assert consumed.consumed_at is not None
    assert consumed.consumed_chat_id == "555"

    settings_row = (
        (await db_session.execute(select(AlertSettings).where(AlertSettings.branch == "filiallar")))
        .scalar_one()
    )
    assert settings_row.telegram_chat_id == "555"


async def test_consume_code_links_super_admin_chat(db_session):
    row = await telegram_link_service.create_super_admin_code(db_session, "actor-1")

    consumed = await telegram_link_service.consume_code(db_session, row.code, "999")

    assert consumed is not None
    global_row = (await db_session.execute(select(TelegramGlobalSettings))).scalar_one()
    assert global_row.super_admin_chat_id == "999"


async def test_consume_code_records_telegram_linked_audit_entry(db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")

    await telegram_link_service.consume_code(db_session, row.code, "555")

    entries = (
        (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.TELEGRAM_LINKED)))
        .scalars()
        .all()
    )
    assert len(entries) == 1
    assert entries[0].branch == "filiallar"


async def test_consume_code_returns_none_for_unknown_code(db_session):
    result = await telegram_link_service.consume_code(db_session, "000000", "555")
    assert result is None


async def test_consume_code_returns_none_for_expired_code(db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    result = await telegram_link_service.consume_code(db_session, row.code, "555")
    assert result is None


async def test_consume_code_returns_none_when_already_consumed(db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    first = await telegram_link_service.consume_code(db_session, row.code, "555")
    assert first is not None

    second = await telegram_link_service.consume_code(db_session, row.code, "666")
    assert second is None
    # The first chat id wins -- a stale/replayed message with an
    # already-consumed code must never silently re-link to a new chat.
    settings_row = (
        (await db_session.execute(select(AlertSettings).where(AlertSettings.branch == "filiallar")))
        .scalar_one()
    )
    assert settings_row.telegram_chat_id == "555"


async def test_generate_code_retries_on_collision(db_session, monkeypatch):
    """Forces the first two candidate codes to collide with an
    already-pending one, then verifies a third, distinct value is used."""
    pending = await telegram_link_service.create_branch_code(db_session, "other-branch", "actor-1")

    values = iter([int(pending.code), int(pending.code), 42])
    monkeypatch.setattr(telegram_link_service.secrets, "randbelow", lambda _n: next(values))

    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    assert row.code == f"{42:0{telegram_link_service.CODE_LENGTH}d}"


async def test_generate_code_gives_up_after_max_attempts(db_session, monkeypatch):
    async def _always_pending(_session, _code):
        return True

    monkeypatch.setattr(telegram_link_service, "_code_is_pending", _always_pending)

    with pytest.raises(RuntimeError):
        await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
