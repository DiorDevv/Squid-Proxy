from app.models.domain_category import DomainCategoryLabel
from app.services.category_inference import infer_category


def test_known_hostname_matches_exactly():
    assert infer_category("netflix.com") == DomainCategoryLabel.VIDEO_STREAMING
    assert infer_category("spotify.com") == DomainCategoryLabel.MUSIC_STREAMING
    assert infer_category("steampowered.com") == DomainCategoryLabel.GAMING


def test_known_hostname_matches_as_subdomain():
    assert infer_category("www.youtube.com") == DomainCategoryLabel.VIDEO_STREAMING
    assert infer_category("api.spotify.com") == DomainCategoryLabel.MUSIC_STREAMING


def test_longest_suffix_wins_over_shorter_general_match():
    # aws.amazon.com is work tooling, not shopping, even though "amazon.com"
    # (shopping) is also a valid suffix match -- the more specific pattern
    # must win.
    assert infer_category("aws.amazon.com") == DomainCategoryLabel.WORK_TOOLS
    assert infer_category("www.amazon.com") == DomainCategoryLabel.SHOPPING
    assert infer_category("amazon.com") == DomainCategoryLabel.SHOPPING


def test_unrelated_domain_containing_a_known_hostname_as_substring_is_not_matched():
    # "amazon.com" must not match via naive substring search against
    # something like "notamazon.com.evil.example" -- only real subdomain
    # boundaries count.
    assert infer_category("notamazon.com") == DomainCategoryLabel.UNCATEGORIZED


def test_gambling_tld_is_recognized_even_for_unknown_hostnames():
    assert infer_category("some-random-site.bet") == DomainCategoryLabel.GAMBLING
    assert infer_category("lucky.casino") == DomainCategoryLabel.GAMBLING


def test_keyword_fallback_for_descriptive_unknown_domains():
    assert infer_category("social-media-timesink.com") == DomainCategoryLabel.SOCIAL_MEDIA
    assert infer_category("streaming-pirate.tv") == DomainCategoryLabel.VIDEO_STREAMING
    assert infer_category("gambling-paradise.bet") == DomainCategoryLabel.GAMBLING


def test_unrecognized_domain_is_uncategorized():
    assert infer_category("free-crypto-miner.top") == DomainCategoryLabel.UNCATEGORIZED
    assert infer_category("internal-wiki.company.local") == DomainCategoryLabel.UNCATEGORIZED


def test_none_or_empty_domain_is_uncategorized():
    assert infer_category(None) == DomainCategoryLabel.UNCATEGORIZED
    assert infer_category("") == DomainCategoryLabel.UNCATEGORIZED


def test_case_insensitive():
    assert infer_category("YouTube.com") == DomainCategoryLabel.VIDEO_STREAMING
