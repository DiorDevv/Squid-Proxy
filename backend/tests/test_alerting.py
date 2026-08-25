"""Tests for the optional webhook alerting service (app/services/alerting.py).
Off by default: only fires when ALERT_WEBHOOK_URL is configured, and only
for anomalies at or above ALERT_MIN_SEVERITY."""

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.services import alerting


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
def _disable_telegram_channel(monkeypatch):
    """maybe_alert() fans out to telegram_alerting.notify() alongside the
    webhook this file tests -- without this, whether these tests hit a real
    DB/Telegram API depends on whatever TELEGRAM_BOT_TOKEN happens to be set
    in the environment (e.g. a real .env for local manual testing), which
    has nothing to do with what this file is testing. Forcing it unset here
    keeps these webhook-only tests hermetic regardless."""
    monkeypatch.setattr(
        alerting.telegram_alerting, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN=None)
    )


async def test_maybe_alert_is_noop_without_webhook_url(monkeypatch):
    monkeypatch.setattr(alerting, "get_settings", lambda: Settings(ALERT_WEBHOOK_URL=None))
    monkeypatch.setattr(alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await alerting.maybe_alert(_anomaly_event(AnomalySeverity.CRITICAL))

    assert _RecordingAsyncClient.calls == []


async def test_maybe_alert_posts_webhook_when_severity_meets_threshold(monkeypatch):
    monkeypatch.setattr(
        alerting,
        "get_settings",
        lambda: Settings(ALERT_WEBHOOK_URL="https://hooks.example.com/alert", ALERT_MIN_SEVERITY="high"),
    )
    monkeypatch.setattr(alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    event = _anomaly_event(AnomalySeverity.HIGH)
    await alerting.maybe_alert(event)

    assert len(_RecordingAsyncClient.calls) == 1
    url, payload = _RecordingAsyncClient.calls[0]
    assert url == "https://hooks.example.com/alert"
    assert payload["title"] == event.title
    assert payload["severity"] == "high"


async def test_maybe_alert_payload_is_slack_compatible_and_includes_branch(monkeypatch):
    """A payload with neither "text" nor "blocks" makes Slack's incoming
    webhook API 400 -- this payload must always carry "text" so pointing
    ALERT_WEBHOOK_URL at a real Slack webhook actually works, not just logs
    a delivery failure every time."""
    monkeypatch.setattr(
        alerting,
        "get_settings",
        lambda: Settings(ALERT_WEBHOOK_URL="https://hooks.slack.com/services/x", ALERT_MIN_SEVERITY="high"),
    )
    monkeypatch.setattr(alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    event = _anomaly_event(
        AnomalySeverity.HIGH, client_ip="10.0.0.5", domain="example.com", branch="filiallar"
    )
    await alerting.maybe_alert(event)

    _, payload = _RecordingAsyncClient.calls[0]
    assert isinstance(payload["text"], str) and payload["text"]
    assert event.title in payload["text"]
    assert "10.0.0.5" in payload["text"]
    assert "example.com" in payload["text"]
    assert "filiallar" in payload["text"]
    assert payload["branch"] == "filiallar"


async def test_maybe_alert_skips_when_severity_below_threshold(monkeypatch):
    monkeypatch.setattr(
        alerting,
        "get_settings",
        lambda: Settings(ALERT_WEBHOOK_URL="https://hooks.example.com/alert", ALERT_MIN_SEVERITY="high"),
    )
    monkeypatch.setattr(alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await alerting.maybe_alert(_anomaly_event(AnomalySeverity.MEDIUM))

    assert _RecordingAsyncClient.calls == []


async def test_maybe_alert_swallows_delivery_failures(monkeypatch):
    class _FailingAsyncClient(_RecordingAsyncClient):
        async def post(self, url: str, json: dict):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(
        alerting,
        "get_settings",
        lambda: Settings(ALERT_WEBHOOK_URL="https://hooks.example.com/alert", ALERT_MIN_SEVERITY="low"),
    )
    monkeypatch.setattr(alerting.httpx, "AsyncClient", _FailingAsyncClient)

    # Must not raise -- a broken webhook can't be allowed to affect the
    # aggregator flush loop that calls this.
    await alerting.maybe_alert(_anomaly_event(AnomalySeverity.LOW))
