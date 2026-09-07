"""Unit tests for app/core/security.py:LoginThrottle -- the per-account
brute-force throttle layered on top of the per-IP login rate limit.
Integration (the /api/auth/login wiring) is in test_auth.py.
"""

import pytest

from app.core import security
from app.core.security import LoginThrottle


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(security.time, "monotonic", lambda: t["now"])
    return t


def test_key_normalizes_case_and_whitespace():
    assert LoginThrottle.key("  Admin@Example.COM ") == "admin@example.com"


def test_below_threshold_always_allowed(clock):
    th = LoginThrottle(failure_threshold=3, throttled_interval_seconds=60)
    for _ in range(2):
        assert th.allow_attempt("a@b.c") is True
        th.record_failure("a@b.c")
    assert th.allow_attempt("a@b.c") is True  # 2 failures < threshold 3


def test_at_threshold_blocks_until_interval_elapses(clock):
    th = LoginThrottle(failure_threshold=3, throttled_interval_seconds=60, failure_window_seconds=900)
    for _ in range(3):
        assert th.allow_attempt("a@b.c") is True
        th.record_failure("a@b.c")

    assert th.allow_attempt("a@b.c") is False  # throttled, last attempt just now
    clock["now"] += 59
    assert th.allow_attempt("a@b.c") is False
    clock["now"] += 1  # 60s since last recorded failure
    assert th.allow_attempt("a@b.c") is True

    # A wrong guess in the throttled window re-arms the interval.
    th.record_failure("a@b.c")
    assert th.allow_attempt("a@b.c") is False


def test_blocked_attempts_do_not_extend_the_wait(clock):
    """A caller hammering while blocked mustn't push their own 1-per-interval
    window further out -- allow_attempt is a pure check."""
    th = LoginThrottle(failure_threshold=1, throttled_interval_seconds=60)
    th.record_failure("a@b.c")
    clock["now"] += 30
    assert th.allow_attempt("a@b.c") is False  # checking doesn't record
    clock["now"] += 30
    assert th.allow_attempt("a@b.c") is True  # 60s since the failure, not since the last check


def test_record_success_clears_the_record(clock):
    th = LoginThrottle(failure_threshold=2, throttled_interval_seconds=60)
    th.record_failure("a@b.c")
    th.record_failure("a@b.c")
    assert th.allow_attempt("a@b.c") is False
    th.record_success("a@b.c")
    assert th.allow_attempt("a@b.c") is True


def test_failures_age_out_of_the_window(clock):
    th = LoginThrottle(failure_threshold=2, failure_window_seconds=900, throttled_interval_seconds=60)
    th.record_failure("a@b.c")
    th.record_failure("a@b.c")
    assert th.allow_attempt("a@b.c") is False
    clock["now"] += 901  # both failures now outside the window
    assert th.allow_attempt("a@b.c") is True


def test_throttle_is_per_account(clock):
    th = LoginThrottle(failure_threshold=1, throttled_interval_seconds=60)
    th.record_failure("victim@b.c")
    assert th.allow_attempt("victim@b.c") is False
    assert th.allow_attempt("someone-else@b.c") is True
