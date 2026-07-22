"""Tests for app.main.create_app's optional Sentry wiring -- everywhere else
unhandled exceptions only go to stdout (see core/exceptions.py), so this is
what closes that gap, but only once a real SENTRY_DSN is actually
configured; the rest of the test suite already exercises the "unset, stays
inert" path implicitly on every run (conftest.py's test_app fixture calls
create_app() with no SENTRY_DSN set)."""

from app.core.config import Settings
from app.main import create_app


def test_create_app_skips_sentry_init_when_dsn_unset(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(SENTRY_DSN=None))
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))

    create_app()

    assert calls == []


def test_create_app_initializes_sentry_when_dsn_set(monkeypatch):
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/0"),
    )
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))

    create_app()

    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
