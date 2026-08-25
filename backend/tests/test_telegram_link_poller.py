"""Tests for the Telegram pairing-code poller
(app/services/telegram_link_poller.py): a message parsed out of Telegram's
getUpdates response is either a bare `/start` (reply with the prompt), a
6-digit code (redeem it via telegram_link_service.consume_code and reply
accordingly), or anything else (ignored)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services import telegram_link_poller, telegram_link_service

_BASE_URL = "https://api.telegram.org/bottest-bot-token"


class _RecordingResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    sent_messages: list[tuple[str, dict]] = []
    updates_to_return: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str, params: dict) -> _RecordingResponse:
        return _RecordingResponse({"result": _FakeAsyncClient.updates_to_return})

    async def post(self, url: str, json: dict) -> _RecordingResponse:
        _FakeAsyncClient.sent_messages.append((url, json))
        return _RecordingResponse({})


def _update(update_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text},
    }


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _FakeAsyncClient.sent_messages = []
    _FakeAsyncClient.updates_to_return = []
    monkeypatch.setattr(telegram_link_poller.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(telegram_link_poller.telegram_alerting.httpx, "AsyncClient", _FakeAsyncClient)
    yield


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch, db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(telegram_link_poller, "AsyncSessionLocal", session_factory)


def _job(monkeypatch) -> telegram_link_poller.TelegramLinkPollerJob:
    job = telegram_link_poller.TelegramLinkPollerJob()
    monkeypatch.setattr(
        telegram_link_poller, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN="test-bot-token")
    )
    return job


async def test_run_is_noop_without_bot_token(monkeypatch):
    job = telegram_link_poller.TelegramLinkPollerJob()
    monkeypatch.setattr(telegram_link_poller, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN=None))

    await job.run()

    assert _FakeAsyncClient.sent_messages == []


async def test_start_command_replies_with_prompt(monkeypatch):
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(1, 111, "/start")]

    await job.run()

    assert len(_FakeAsyncClient.sent_messages) == 1
    _, payload = _FakeAsyncClient.sent_messages[0]
    assert payload["chat_id"] == "111"
    assert payload["text"] == telegram_link_poller._PROMPT_TEXT
    assert job._offset == 2


async def test_valid_branch_code_links_chat_and_replies_success(monkeypatch, db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(5, 222, row.code)]

    await job.run()

    assert len(_FakeAsyncClient.sent_messages) == 1
    _, payload = _FakeAsyncClient.sent_messages[0]
    assert payload["chat_id"] == "222"
    assert "filiallar" in payload["text"]
    assert payload["text"].startswith("✅")


async def test_valid_super_admin_code_replies_success(monkeypatch, db_session):
    row = await telegram_link_service.create_super_admin_code(db_session, "actor-1")
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(9, 333, row.code)]

    await job.run()

    _, payload = _FakeAsyncClient.sent_messages[0]
    assert payload["chat_id"] == "333"
    assert payload["text"] == telegram_link_poller._SUCCESS_SUPER_ADMIN_TEXT


async def test_invalid_code_replies_with_error(monkeypatch):
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(3, 444, "000000")]

    await job.run()

    _, payload = _FakeAsyncClient.sent_messages[0]
    assert payload["chat_id"] == "444"
    assert payload["text"] == telegram_link_poller._INVALID_CODE_TEXT


async def test_unrelated_text_is_ignored(monkeypatch):
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(4, 555, "hello there")]

    await job.run()

    assert _FakeAsyncClient.sent_messages == []


async def test_start_with_code_payload_is_treated_as_the_code(monkeypatch, db_session):
    row = await telegram_link_service.create_branch_code(db_session, "filiallar", "actor-1")
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(7, 666, f"/start {row.code}")]

    await job.run()

    _, payload = _FakeAsyncClient.sent_messages[0]
    assert payload["text"].startswith("✅")


async def test_offset_advances_past_processed_updates(monkeypatch):
    job = _job(monkeypatch)
    _FakeAsyncClient.updates_to_return = [_update(10, 1, "/start"), _update(11, 2, "/start")]

    await job.run()

    assert job._offset == 12
