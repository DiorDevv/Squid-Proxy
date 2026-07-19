"""Tests for the "is it time to send the scheduled report yet" logic
(app/services/report_scheduler.py). Patches report_service.generate_and_send_report
itself (already covered by its own tests) rather than mocking smtplib again
here -- this file is purely about the scheduling decision."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.report_schedule_state import ReportScheduleState
from app.services import report_scheduler as scheduler_module
from app.services.report_scheduler import STATE_ROW_ID, ReportScheduler


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", lambda: db_session)


async def test_check_is_noop_when_schedule_disabled(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: Settings(REPORT_SCHEDULE="disabled", REPORT_RECIPIENTS=["a@b.com"])
    )
    sent_calls = []
    monkeypatch.setattr(
        scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=True)
    )

    await ReportScheduler().check()

    assert sent_calls == []


async def test_check_is_noop_when_no_recipients(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: Settings(REPORT_SCHEDULE="daily", REPORT_RECIPIENTS=[])
    )
    sent_calls = []
    monkeypatch.setattr(scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=True))

    await ReportScheduler().check()

    assert sent_calls == []


async def test_check_sends_on_first_run_with_no_prior_state(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(REPORT_SCHEDULE="daily", REPORT_RECIPIENTS=["a@b.com"]),
    )
    sent_calls = []
    monkeypatch.setattr(scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=True))

    await ReportScheduler().check()

    assert len(sent_calls) == 1
    row = (
        await db_session.execute(select(ReportScheduleState).where(ReportScheduleState.id == STATE_ROW_ID))
    ).scalar_one()
    assert row.last_sent_at is not None


async def test_check_does_not_send_again_before_interval_elapses(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(REPORT_SCHEDULE="daily", REPORT_RECIPIENTS=["a@b.com"]),
    )
    db_session.add(ReportScheduleState(id=STATE_ROW_ID, last_sent_at=datetime.now(UTC) - timedelta(hours=1)))
    await db_session.commit()

    sent_calls = []
    monkeypatch.setattr(scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=True))

    await ReportScheduler().check()

    assert sent_calls == []


async def test_check_sends_again_once_daily_interval_has_elapsed(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(REPORT_SCHEDULE="daily", REPORT_RECIPIENTS=["a@b.com"]),
    )
    db_session.add(ReportScheduleState(id=STATE_ROW_ID, last_sent_at=datetime.now(UTC) - timedelta(days=2)))
    await db_session.commit()

    sent_calls = []
    monkeypatch.setattr(scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=True))

    await ReportScheduler().check()

    assert len(sent_calls) == 1


async def test_check_does_not_update_state_when_send_fails_noop(monkeypatch, db_session: AsyncSession):
    """generate_and_send_report returning False (its own internal no-op,
    e.g. recipients vanished between the settings check and the send)
    shouldn't advance last_sent_at."""
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(REPORT_SCHEDULE="daily", REPORT_RECIPIENTS=["a@b.com"]),
    )
    sent_calls = []
    monkeypatch.setattr(scheduler_module, "generate_and_send_report", _fake_send(sent_calls, result=False))

    await ReportScheduler().check()

    row = (
        await db_session.execute(select(ReportScheduleState).where(ReportScheduleState.id == STATE_ROW_ID))
    ).scalar_one_or_none()
    assert row is None


def _fake_send(calls: list, result: bool):
    async def _fake(session, since, until):
        calls.append((since, until))
        return result

    return _fake
