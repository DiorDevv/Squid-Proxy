"""Tests for Ut1BlacklistScheduler.check() -- patches ut1_blacklist.refresh
itself (a real refresh does network I/O and CPU-heavy hashing, covered by
its own tests in test_ut1_blacklist.py) rather than exercising either here."""

from app.core.config import Settings
from app.services import category_inference
from app.services import ut1_scheduler as scheduler_module
from app.services.ut1_blacklist import CompactDomainSet, Ut1Blacklist
from app.services.ut1_scheduler import Ut1BlacklistScheduler


def _fake_refresh(blacklist: Ut1Blacklist, calls: list):
    def _fake(data_dir, mirror_url):
        calls.append((data_dir, mirror_url))
        return blacklist

    return _fake


async def test_check_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings(UT1_ENABLED=False))
    calls: list = []
    monkeypatch.setattr(scheduler_module, "refresh", _fake_refresh(Ut1Blacklist({}), calls))

    await Ut1BlacklistScheduler().check()

    assert calls == []


async def test_check_refreshes_and_installs_blacklist_when_enabled(monkeypatch):
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(UT1_ENABLED=True, UT1_DATA_DIR="./some-dir", UT1_MIRROR_URL="https://example.test/blacklists.tar.gz"),
    )
    domain_set = CompactDomainSet()
    domain_set.add_lines(["scheduler-test-domain.example"])
    domain_set.finalize()
    from app.models.domain_category import DomainCategoryLabel

    blacklist = Ut1Blacklist({DomainCategoryLabel.GAMBLING: domain_set})
    calls: list = []
    monkeypatch.setattr(scheduler_module, "refresh", _fake_refresh(blacklist, calls))

    try:
        await Ut1BlacklistScheduler().check()

        assert len(calls) == 1
        assert str(calls[0][0]) == "some-dir"
        assert calls[0][1] == "https://example.test/blacklists.tar.gz"
        assert (
            category_inference.infer_category("scheduler-test-domain.example")
            == DomainCategoryLabel.GAMBLING
        )
    finally:
        category_inference.set_ut1_blacklist(None)
