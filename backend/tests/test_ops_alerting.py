"""Tests for the operator-facing infra-failure alerting service
(app/services/ops_alerting.py). Off by default: only fires when
OPS_ALERT_WEBHOOK_URL (or, as a fallback, ALERT_WEBHOOK_URL) is
configured. Unlike app/services/alerting.py, there's no severity
threshold -- every call site already only fires on a real failure."""

from app.core.config import Settings
from app.services import ops_alerting


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


def setup_function() -> None:
    _RecordingAsyncClient.calls = []


async def test_notify_operator_failure_is_noop_without_any_webhook_url(monkeypatch):
    monkeypatch.setattr(
        ops_alerting,
        "get_settings",
        lambda: Settings(OPS_ALERT_WEBHOOK_URL=None, ALERT_WEBHOOK_URL=None),
    )
    monkeypatch.setattr(ops_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await ops_alerting.notify_operator_failure("retention", "Retention purge failed")

    assert _RecordingAsyncClient.calls == []


async def test_notify_operator_failure_posts_to_ops_webhook_when_configured(monkeypatch):
    monkeypatch.setattr(
        ops_alerting,
        "get_settings",
        lambda: Settings(OPS_ALERT_WEBHOOK_URL="https://hooks.example.com/ops", ALERT_WEBHOOK_URL=None),
    )
    monkeypatch.setattr(ops_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await ops_alerting.notify_operator_failure("log_tailer:filiallar", "Log tailer died")

    assert len(_RecordingAsyncClient.calls) == 1
    url, payload = _RecordingAsyncClient.calls[0]
    assert url == "https://hooks.example.com/ops"
    assert payload["source"] == "log_tailer:filiallar"
    assert payload["description"] == "Log tailer died"
    assert payload["severity"] == "high"
    assert "generated_at" in payload
    # A payload with neither "text" nor "blocks" makes Slack's incoming
    # webhook API 400 -- must always carry "text".
    assert isinstance(payload["text"], str) and payload["text"]
    assert "log_tailer:filiallar" in payload["text"]
    assert "Log tailer died" in payload["text"]


async def test_notify_operator_failure_falls_back_to_alert_webhook_url(monkeypatch):
    monkeypatch.setattr(
        ops_alerting,
        "get_settings",
        lambda: Settings(OPS_ALERT_WEBHOOK_URL=None, ALERT_WEBHOOK_URL="https://hooks.example.com/anomaly"),
    )
    monkeypatch.setattr(ops_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await ops_alerting.notify_operator_failure("backup", "Backup failed")

    assert len(_RecordingAsyncClient.calls) == 1
    url, _ = _RecordingAsyncClient.calls[0]
    assert url == "https://hooks.example.com/anomaly"


async def test_notify_operator_failure_prefers_ops_webhook_over_alert_webhook(monkeypatch):
    monkeypatch.setattr(
        ops_alerting,
        "get_settings",
        lambda: Settings(
            OPS_ALERT_WEBHOOK_URL="https://hooks.example.com/ops",
            ALERT_WEBHOOK_URL="https://hooks.example.com/anomaly",
        ),
    )
    monkeypatch.setattr(ops_alerting.httpx, "AsyncClient", _RecordingAsyncClient)

    await ops_alerting.notify_operator_failure("retention", "Retention purge failed")

    url, _ = _RecordingAsyncClient.calls[0]
    assert url == "https://hooks.example.com/ops"


async def test_notify_operator_failure_swallows_delivery_failures(monkeypatch):
    class _FailingAsyncClient(_RecordingAsyncClient):
        async def post(self, url: str, json: dict):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(
        ops_alerting,
        "get_settings",
        lambda: Settings(OPS_ALERT_WEBHOOK_URL="https://hooks.example.com/ops"),
    )
    monkeypatch.setattr(ops_alerting.httpx, "AsyncClient", _FailingAsyncClient)

    # Must not raise -- a broken webhook can't be allowed to affect the
    # background job (or backup script) whose except block calls this.
    await ops_alerting.notify_operator_failure("retention", "Retention purge failed")
