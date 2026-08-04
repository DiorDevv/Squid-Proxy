"""Tests for the shared IntervalJob base class (app/services/interval_job.py)
directly, via a small concrete test-double subclass -- covers start/stop/
error-catching/run_immediately_on_start once here instead of only ever
indirectly through 8 separate subclasses' own tests."""

import asyncio

import pytest

from app.services import interval_job as interval_job_module
from app.services.interval_job import IntervalJob


class _CountingJob(IntervalJob):
    job_name = "counting-job"
    failure_source_tag = "counting_job"
    failure_log_message = "Counting job failed; will retry next interval"

    def __init__(self, interval_seconds: float, should_fail: bool = False) -> None:
        super().__init__(interval_seconds)
        self.run_count = 0
        self.should_fail = should_fail

    async def run(self) -> None:
        self.run_count += 1
        if self.should_fail:
            raise RuntimeError("boom")


async def test_run_forever_calls_run_on_each_interval_tick():
    job = _CountingJob(interval_seconds=0.01)
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()

    assert job.run_count >= 2


async def test_stop_prevents_further_runs():
    job = _CountingJob(interval_seconds=0.01)
    job.start()
    await asyncio.sleep(0.03)
    await job.stop()
    count_after_stop = job.run_count

    await asyncio.sleep(0.03)
    assert job.run_count == count_after_stop


async def test_run_immediately_on_start_fires_before_first_interval():
    class _ImmediateJob(_CountingJob):
        run_immediately_on_start = True

    job = _ImmediateJob(interval_seconds=60)
    job.start()
    await asyncio.sleep(0.02)
    await job.stop()

    assert job.run_count == 1


async def test_run_immediately_on_start_defaults_false():
    job = _CountingJob(interval_seconds=60)
    job.start()
    await asyncio.sleep(0.02)
    await job.stop()

    assert job.run_count == 0


async def test_run_catching_errors_notifies_operator_on_failure(monkeypatch):
    """Proves the wiring (not just app/services/ops_alerting.py in
    isolation): a real run() failure must reach notify_operator_failure,
    same as it already reaches logger.exception."""
    job = _CountingJob(interval_seconds=60, should_fail=True)

    calls = []

    async def _fake_notify(source: str, message: str) -> None:
        calls.append((source, message))

    monkeypatch.setattr(interval_job_module, "notify_operator_failure", _fake_notify)

    # Must not raise -- a single bad run can't be allowed to stop the job.
    await job._run_catching_errors()

    assert len(calls) == 1
    source, message = calls[0]
    assert source == "counting_job"
    assert "failed" in message.lower()


async def test_a_failing_run_does_not_stop_subsequent_ticks(monkeypatch):
    async def _noop_notify(source: str, message: str) -> None:
        return None

    monkeypatch.setattr(interval_job_module, "notify_operator_failure", _noop_notify)

    job = _CountingJob(interval_seconds=0.01, should_fail=True)
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()

    assert job.run_count >= 2


def test_run_is_abstract():
    with pytest.raises(TypeError):
        IntervalJob(interval_seconds=60)  # type: ignore[abstract]
