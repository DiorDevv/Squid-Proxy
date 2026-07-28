from pathlib import Path

import pytest

from app.models.domain_category import DomainCategoryLabel
from app.services.ut1_blacklist import (
    CompactDomainSet,
    Ut1Blacklist,
    _domain_and_ancestors,
    build_from_dir,
)


def test_compact_domain_set_contains_added_domains():
    domain_set = CompactDomainSet()
    domain_set.add_lines(["example.com\n", "another-site.org\n", "\n", "  \n"])
    domain_set.finalize()

    assert "example.com" in domain_set
    assert "another-site.org" in domain_set
    assert "not-in-the-set.com" not in domain_set
    assert len(domain_set) == 2


def test_domain_and_ancestors_stops_at_two_labels():
    assert list(_domain_and_ancestors("a.b.example.com")) == [
        "a.b.example.com",
        "b.example.com",
        "example.com",
    ]


def test_blacklist_categorize_matches_subdomains():
    domain_set = CompactDomainSet()
    domain_set.add_lines(["gambling-example.com"])
    domain_set.finalize()
    blacklist = Ut1Blacklist({DomainCategoryLabel.GAMBLING: domain_set})

    assert blacklist.categorize("gambling-example.com") == DomainCategoryLabel.GAMBLING
    assert blacklist.categorize("www.gambling-example.com") == DomainCategoryLabel.GAMBLING
    assert blacklist.categorize("unrelated.com") is None


def test_blacklist_categorize_is_case_insensitive():
    domain_set = CompactDomainSet()
    domain_set.add_lines(["example.com"])
    domain_set.finalize()
    blacklist = Ut1Blacklist({DomainCategoryLabel.ADULT_CONTENT: domain_set})

    assert blacklist.categorize("EXAMPLE.com") == DomainCategoryLabel.ADULT_CONTENT


def test_blacklist_checks_labels_in_fixed_priority_order():
    # Same domain filed under two mapped categories -- adult_content is
    # checked first in _LABEL_CHECK_ORDER, so it should win regardless of
    # dict insertion order.
    adult_set = CompactDomainSet()
    adult_set.add_lines(["overlap.example"])
    adult_set.finalize()
    shopping_set = CompactDomainSet()
    shopping_set.add_lines(["overlap.example"])
    shopping_set.finalize()

    blacklist = Ut1Blacklist(
        {
            DomainCategoryLabel.SHOPPING: shopping_set,
            DomainCategoryLabel.ADULT_CONTENT: adult_set,
        }
    )

    assert blacklist.categorize("overlap.example") == DomainCategoryLabel.ADULT_CONTENT


def test_build_from_dir_skips_missing_categories(tmp_path: Path):
    # Only "gambling" has an extracted file; "adult", "games", etc. are
    # missing (e.g. never downloaded yet, or that category was briefly
    # unavailable upstream) -- build_from_dir must not raise, just omit them.
    gambling_dir = tmp_path / "gambling"
    gambling_dir.mkdir()
    (gambling_dir / "domains").write_text("bet-site.example\nanother-bet.example\n")

    blacklist = build_from_dir(tmp_path)

    assert blacklist.categorize("bet-site.example") == DomainCategoryLabel.GAMBLING
    assert blacklist.categorize("totally-unrelated.example") is None


def test_build_from_dir_merges_multiple_categories_into_one_label(tmp_path: Path):
    # "gambling" and "arjel" both map to GAMBLING -- entries from either
    # should be found under that one label.
    (tmp_path / "gambling").mkdir()
    (tmp_path / "gambling" / "domains").write_text("from-gambling.example\n")
    (tmp_path / "arjel").mkdir()
    (tmp_path / "arjel" / "domains").write_text("from-arjel.example\n")

    blacklist = build_from_dir(tmp_path)

    assert blacklist.categorize("from-gambling.example") == DomainCategoryLabel.GAMBLING
    assert blacklist.categorize("from-arjel.example") == DomainCategoryLabel.GAMBLING


def test_build_from_dir_maps_radio_to_music_streaming(tmp_path: Path):
    # UT1's "radio" folder (internet radio stations) is distinct from
    # "audio-video" (video-first) -- without this, radio stations would
    # never be reachable via UT1's music_streaming label at all.
    (tmp_path / "radio").mkdir()
    (tmp_path / "radio" / "domains").write_text("some-radio-station.example\n")

    blacklist = build_from_dir(tmp_path)

    assert blacklist.categorize("some-radio-station.example") == DomainCategoryLabel.MUSIC_STREAMING


@pytest.fixture(autouse=True)
def _reset_category_inference_ut1_state():
    """category_inference.py holds the active Ut1Blacklist (and an
    lru_cache keyed on domain) as module-level state -- shared across every
    test in the process, not just this file. Reset both around each test
    here so nothing leaks into unrelated tests (e.g. test_category_inference.py's
    UNCATEGORIZED assertions, which would break if a UT1 blacklist set by a
    test here were still active)."""
    from app.services import category_inference

    category_inference.set_ut1_blacklist(None)
    yield
    category_inference.set_ut1_blacklist(None)


def test_infer_category_uses_ut1_blacklist_when_set():
    from app.services.category_inference import infer_category, set_ut1_blacklist

    domain_set = CompactDomainSet()
    domain_set.add_lines(["ut1-only-domain.example"])
    domain_set.finalize()
    set_ut1_blacklist(Ut1Blacklist({DomainCategoryLabel.GAMBLING: domain_set}))

    assert infer_category("ut1-only-domain.example") == DomainCategoryLabel.GAMBLING


def test_curated_hostname_tier_still_wins_over_ut1():
    from app.services.category_inference import infer_category, set_ut1_blacklist

    # netflix.com is in the curated _KNOWN_HOSTNAMES list (video_streaming);
    # a UT1 list wrongly filing it under gambling must not override that.
    domain_set = CompactDomainSet()
    domain_set.add_lines(["netflix.com"])
    domain_set.finalize()
    set_ut1_blacklist(Ut1Blacklist({DomainCategoryLabel.GAMBLING: domain_set}))

    assert infer_category("netflix.com") == DomainCategoryLabel.VIDEO_STREAMING


def test_setting_ut1_blacklist_clears_the_inference_cache():
    from app.services.category_inference import infer_category, set_ut1_blacklist

    domain = "cache-clear-test-domain.example"
    assert infer_category(domain) == DomainCategoryLabel.UNCATEGORIZED

    domain_set = CompactDomainSet()
    domain_set.add_lines([domain])
    domain_set.finalize()
    set_ut1_blacklist(Ut1Blacklist({DomainCategoryLabel.SHOPPING: domain_set}))

    assert infer_category(domain) == DomainCategoryLabel.SHOPPING
