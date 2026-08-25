"""Tests for the optional Telegram alerting service
(app/services/telegram_alerting.py). Off by default: only fires when
TELEGRAM_BOT_TOKEN is configured, and only for anomalies at or above
ALERT_MIN_SEVERITY. Delivers to the anomaly's branch's own chat
(AlertSettings.telegram_chat_id) and/or TELEGRAM_SUPER_ADMIN_CHAT_ID,
deduplicated when both resolve to the same chat id."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.alert_settings import AlertSettings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.services import telegram_alerting


def _anomaly_event(
    severity: AnomalySeverity, *, client_ip=None, domain=None, branch="filiallar"
) -> AnomalyEvent:
    return AnomalyEvent(
        id="evt-1",
        generated_at=datetime.now(UTC),
        title="Traffic spike detected",
        description="100 requests vs a baseline of ~10.",
        severity=severity,
        client_ip=client_ip,
        domain=domain,
        branch=branch,
    )


class _RecordingResponse:
    def raise_for_status(self) -> None:
        return None


class _RecordingAsyncClient:
    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url: str, json: dict) -> _RecordingResponse:
        _RecordingAsyncClient.calls.append((url, json))
        return _RecordingResponse()


@pytest.fixture(autouse=True)
def _reset_recorded_calls():
    _RecordingAsyncClient.calls = []
    yield


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch, db_engine):
    # telegram_alerting imports AsyncSessionLocal directly at module scope
    # (like the interval monitor jobs do), so it needs its own patch onto
    # the test DB engine -- patching app.models.db doesn't reach it.
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(telegram_alerting, "AsyncSessionLocal", session_factory)


async def test_notify_is_noop_without_bot_token(monkeypatch):
    monkeypatch.setattr(telegram_alerting, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN=None))
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.CRITICAL))

    assert _RecordingAsyncClient.calls == []


async def test_notify_skips_when_severity_below_threshold(monkeypatch):
    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(
            TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID="999", ALERT_MIN_SEVERITY="high"
        ),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.MEDIUM))

    assert _RecordingAsyncClient.calls == []


async def test_notify_sends_to_super_admin_chat(monkeypatch):
    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(
            TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID="999", ALERT_MIN_SEVERITY="high"
        ),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    event = _anomaly_event(AnomalySeverity.HIGH, branch=None)
    await telegram_alerting.notify(event)

    assert len(_RecordingAsyncClient.calls) == 1
    url, payload = _RecordingAsyncClient.calls[0]
    assert url == "https://api.telegram.org/botbot-token/sendMessage"
    assert payload["chat_id"] == "999"
    assert payload["parse_mode"] == "HTML"
    assert event.title in payload["text"]


async def test_notify_sends_to_branch_chat(monkeypatch, db_session):
    db_session.add(AlertSettings(branch="filiallar", telegram_chat_id="123"))
    await db_session.commit()

    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID=None, ALERT_MIN_SEVERITY="high"),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.HIGH, branch="filiallar"))

    assert len(_RecordingAsyncClient.calls) == 1
    _, payload = _RecordingAsyncClient.calls[0]
    assert payload["chat_id"] == "123"


async def test_notify_sends_to_both_super_admin_and_branch_chat(monkeypatch, db_session):
    db_session.add(AlertSettings(branch="filiallar", telegram_chat_id="123"))
    await db_session.commit()

    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(
            TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID="999", ALERT_MIN_SEVERITY="high"
        ),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.HIGH, branch="filiallar"))

    chat_ids = {payload["chat_id"] for _, payload in _RecordingAsyncClient.calls}
    assert chat_ids == {"123", "999"}


async def test_notify_dedupes_when_branch_chat_equals_super_admin_chat(monkeypatch, db_session):
    db_session.add(AlertSettings(branch="filiallar", telegram_chat_id="999"))
    await db_session.commit()

    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(
            TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID="999", ALERT_MIN_SEVERITY="high"
        ),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.HIGH, branch="filiallar"))

    assert len(_RecordingAsyncClient.calls) == 1


async def test_notify_swallows_delivery_failures(monkeypatch):
    class _FailingAsyncClient(_RecordingAsyncClient):
        async def post(self, url: str, json: dict):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(
        telegram_alerting,
        "get_settings",
        lambda: Settings(
            TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_SUPER_ADMIN_CHAT_ID="999", ALERT_MIN_SEVERITY="low"
        ),
    )
    monkeypatch.setattr(telegram_alerting.httpx, "AsyncClient", _FailingAsyncClient)

    # Must not raise -- a broken chat/bot can't be allowed to affect the
    # aggregator flush loop that calls this (via alerting.maybe_alert).
    await telegram_alerting.notify(_anomaly_event(AnomalySeverity.LOW))
