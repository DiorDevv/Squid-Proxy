"""Tests for report generation/rendering and the SMTP send path
(app/services/report_service.py). No real SMTP server is available in this
environment, so smtplib.SMTP is mocked -- see tests/test_alerting.py for
the same "record the call, assert on it" pattern used for the webhook."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import report_service


def _raw_event(domain: str = "example.com", timestamp: datetime | None = None) -> RawEvent:
    return RawEvent(
        timestamp=timestamp or datetime.now(UTC),
        duration_ms=1,
        client_ip="10.0.0.1",
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url=f"http://{domain}/",
        domain=domain,
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=False,
    )


class _RecordingSMTP:
    calls: list[dict] = []
    started_tls = False
    logged_in_as: tuple[str, str] | None = None

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def starttls(self):
        _RecordingSMTP.started_tls = True

    def login(self, username, password):
        _RecordingSMTP.logged_in_as = (username, password)

    def sendmail(self, from_addr, to_addrs, msg):
        _RecordingSMTP.calls.append({"from": from_addr, "to": to_addrs, "msg": msg})


@pytest.fixture(autouse=True)
def _reset_recorded_calls():
    _RecordingSMTP.calls = []
    _RecordingSMTP.started_tls = False
    _RecordingSMTP.logged_in_as = None
    yield


async def test_generate_report_includes_seeded_data(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            MinuteAggregate(
                bucket_ts=now, total_requests=10, blocked_requests=2, allowed_requests=8, total_bytes=100
            ),
            DomainMinuteAggregate(bucket_ts=now, domain="example.com", request_count=10, blocked_count=2),
        ]
    )
    await db_session.commit()

    html = await report_service.generate_report(db_session, now - timedelta(hours=1), now + timedelta(hours=1))

    assert "example.com" in html
    assert "10" in html  # total_requests


def test_render_report_html_escapes_malicious_domain_names():
    from app.schemas.domains import DomainStat
    from app.schemas.summary import SummaryResponse

    now = datetime.now(UTC)
    summary = SummaryResponse(
        range=None,
        since=now,
        until=now,
        total_requests=1,
        blocked_requests=0,
        allowed_requests=1,
        active_client_count=1,
        active_user_count=0,
    )
    malicious = DomainStat(
        domain="<script>alert(1)</script>", request_count=1, blocked_count=0, total_bytes=1, category="other"
    )

    html = report_service.render_report_html(now, now, summary, [malicious], [], [], [])

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_send_report_email_raises_when_smtp_not_configured(monkeypatch):
    monkeypatch.setattr(report_service, "get_settings", lambda: Settings(SMTP_HOST=None))

    with pytest.raises(RuntimeError):
        report_service.send_report_email(["a@example.com"], "subject", "<html></html>")


def test_send_report_email_sends_via_smtp(monkeypatch):
    monkeypatch.setattr(
        report_service,
        "get_settings",
        lambda: Settings(
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_FROM_ADDRESS="squid-watch@example.com",
            SMTP_USERNAME="user",
            SMTP_PASSWORD="pass",
            SMTP_USE_TLS=True,
        ),
    )
    monkeypatch.setattr(report_service.smtplib, "SMTP", _RecordingSMTP)

    report_service.send_report_email(
        ["a@example.com", "b@example.com"], "Squid Watch report", "<html>body</html>", csv_attachment="col1\nval1"
    )

    assert len(_RecordingSMTP.calls) == 1
    call = _RecordingSMTP.calls[0]
    assert call["from"] == "squid-watch@example.com"
    assert call["to"] == ["a@example.com", "b@example.com"]
    assert "Squid Watch report" in call["msg"]
    assert _RecordingSMTP.started_tls is True
    assert _RecordingSMTP.logged_in_as == ("user", "pass")


async def test_generate_and_send_report_is_noop_without_recipients(monkeypatch, db_session: AsyncSession):
    monkeypatch.setattr(report_service, "get_settings", lambda: Settings(REPORT_RECIPIENTS=[]))
    monkeypatch.setattr(report_service.smtplib, "SMTP", _RecordingSMTP)

    now = datetime.now(UTC)
    sent = await report_service.generate_and_send_report(db_session, now - timedelta(hours=1), now)

    assert sent is False
    assert _RecordingSMTP.calls == []


async def test_generate_and_send_report_sends_when_configured(monkeypatch, db_session: AsyncSession):
    monkeypatch.setattr(
        report_service,
        "get_settings",
        lambda: Settings(
            REPORT_RECIPIENTS=["compliance@example.com"],
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_ADDRESS="squid-watch@example.com",
        ),
    )
    monkeypatch.setattr(report_service.smtplib, "SMTP", _RecordingSMTP)

    db_session.add(_raw_event())
    await db_session.commit()

    now = datetime.now(UTC)
    sent = await report_service.generate_and_send_report(db_session, now - timedelta(hours=1), now)

    assert sent is True
    assert len(_RecordingSMTP.calls) == 1
    assert _RecordingSMTP.calls[0]["to"] == ["compliance@example.com"]
