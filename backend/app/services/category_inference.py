"""Best-effort automatic domain categorization.

This is a *default*, not an override: app/services/domain_category_service.py's
admin-assigned categories always take precedence (see get_effective_category
in stats_service.py, the only caller that combines the two). Without this,
a real deployment with hundreds of distinct domains would start with
everything dumped in "uncategorized" until an admin manually tags each one,
which doesn't scale -- this exists purely to make that starting point useful.

Three tiers, checked in order, first match wins:
  1. Known hostnames (longest suffix match, so "aws.amazon.com" resolves to
     work_tools even though the shorter "amazon.com" suffix matches shopping)
  2. Category-indicating TLDs (weaker signal, but reliable for a handful of
     categories where the TLD itself is a strong hint, e.g. gambling sites
     disproportionately use .bet/.casino/.poker)
  3. Keyword substrings in the hostname itself (weakest signal -- catches
     descriptive names a known-hostname list will never cover, at the cost
     of occasional false positives)

Never raises and never returns anything but a valid DomainCategoryLabel;
an unrecognized domain is simply UNCATEGORIZED, the same as if an admin
hadn't gotten to it yet.
"""

from functools import lru_cache

from app.models.domain_category import DomainCategoryLabel

_KNOWN_HOSTNAMES: dict[str, DomainCategoryLabel] = {
    # --- Video streaming ---
    "youtube.com": DomainCategoryLabel.VIDEO_STREAMING,
    "youtu.be": DomainCategoryLabel.VIDEO_STREAMING,
    "netflix.com": DomainCategoryLabel.VIDEO_STREAMING,
    "twitch.tv": DomainCategoryLabel.VIDEO_STREAMING,
    "hulu.com": DomainCategoryLabel.VIDEO_STREAMING,
    "disneyplus.com": DomainCategoryLabel.VIDEO_STREAMING,
    "primevideo.com": DomainCategoryLabel.VIDEO_STREAMING,
    "vimeo.com": DomainCategoryLabel.VIDEO_STREAMING,
    "dailymotion.com": DomainCategoryLabel.VIDEO_STREAMING,
    "hbomax.com": DomainCategoryLabel.VIDEO_STREAMING,
    "crunchyroll.com": DomainCategoryLabel.VIDEO_STREAMING,
    "kinopoisk.ru": DomainCategoryLabel.VIDEO_STREAMING,
    # --- Music streaming ---
    "spotify.com": DomainCategoryLabel.MUSIC_STREAMING,
    "soundcloud.com": DomainCategoryLabel.MUSIC_STREAMING,
    "music.apple.com": DomainCategoryLabel.MUSIC_STREAMING,
    "deezer.com": DomainCategoryLabel.MUSIC_STREAMING,
    "tidal.com": DomainCategoryLabel.MUSIC_STREAMING,
    "pandora.com": DomainCategoryLabel.MUSIC_STREAMING,
    "iheart.com": DomainCategoryLabel.MUSIC_STREAMING,
    "music.yandex.ru": DomainCategoryLabel.MUSIC_STREAMING,
    # --- Gaming ---
    "steampowered.com": DomainCategoryLabel.GAMING,
    "steamcommunity.com": DomainCategoryLabel.GAMING,
    "epicgames.com": DomainCategoryLabel.GAMING,
    "roblox.com": DomainCategoryLabel.GAMING,
    "riotgames.com": DomainCategoryLabel.GAMING,
    "leagueoflegends.com": DomainCategoryLabel.GAMING,
    "battle.net": DomainCategoryLabel.GAMING,
    "blizzard.com": DomainCategoryLabel.GAMING,
    "ea.com": DomainCategoryLabel.GAMING,
    "origin.com": DomainCategoryLabel.GAMING,
    "minecraft.net": DomainCategoryLabel.GAMING,
    "xbox.com": DomainCategoryLabel.GAMING,
    "playstation.com": DomainCategoryLabel.GAMING,
    "nintendo.com": DomainCategoryLabel.GAMING,
    # --- Social media ---
    "facebook.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "instagram.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "twitter.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "x.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "tiktok.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "reddit.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "linkedin.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "snapchat.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "pinterest.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "discord.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "telegram.org": DomainCategoryLabel.SOCIAL_MEDIA,
    "web.telegram.org": DomainCategoryLabel.SOCIAL_MEDIA,
    "whatsapp.com": DomainCategoryLabel.SOCIAL_MEDIA,
    "vk.com": DomainCategoryLabel.SOCIAL_MEDIA,
    # --- Shopping ---
    "amazon.com": DomainCategoryLabel.SHOPPING,
    "ebay.com": DomainCategoryLabel.SHOPPING,
    "aliexpress.com": DomainCategoryLabel.SHOPPING,
    "etsy.com": DomainCategoryLabel.SHOPPING,
    "walmart.com": DomainCategoryLabel.SHOPPING,
    "target.com": DomainCategoryLabel.SHOPPING,
    "wildberries.ru": DomainCategoryLabel.SHOPPING,
    # --- News ---
    "cnn.com": DomainCategoryLabel.NEWS,
    "bbc.com": DomainCategoryLabel.NEWS,
    "bbc.co.uk": DomainCategoryLabel.NEWS,
    "nytimes.com": DomainCategoryLabel.NEWS,
    "reuters.com": DomainCategoryLabel.NEWS,
    "bloomberg.com": DomainCategoryLabel.NEWS,
    "foxnews.com": DomainCategoryLabel.NEWS,
    "news.ycombinator.com": DomainCategoryLabel.NEWS,
    # --- Gambling ---
    "bet365.com": DomainCategoryLabel.GAMBLING,
    "draftkings.com": DomainCategoryLabel.GAMBLING,
    "fanduel.com": DomainCategoryLabel.GAMBLING,
    "pokerstars.com": DomainCategoryLabel.GAMBLING,
    # --- Work tools (checked before the shorter "amazon.com"/etc. above via
    # longest-suffix-match, so e.g. aws.amazon.com doesn't land in shopping) ---
    "aws.amazon.com": DomainCategoryLabel.WORK_TOOLS,
    "slack.com": DomainCategoryLabel.WORK_TOOLS,
    "zoom.us": DomainCategoryLabel.WORK_TOOLS,
    "github.com": DomainCategoryLabel.WORK_TOOLS,
    "gitlab.com": DomainCategoryLabel.WORK_TOOLS,
    "atlassian.com": DomainCategoryLabel.WORK_TOOLS,
    "atlassian.net": DomainCategoryLabel.WORK_TOOLS,
    "office.com": DomainCategoryLabel.WORK_TOOLS,
    "office365.com": DomainCategoryLabel.WORK_TOOLS,
    "teams.microsoft.com": DomainCategoryLabel.WORK_TOOLS,
    "sharepoint.com": DomainCategoryLabel.WORK_TOOLS,
    "docs.google.com": DomainCategoryLabel.WORK_TOOLS,
    "drive.google.com": DomainCategoryLabel.WORK_TOOLS,
    "cloud.google.com": DomainCategoryLabel.WORK_TOOLS,
    "dropbox.com": DomainCategoryLabel.WORK_TOOLS,
    "notion.so": DomainCategoryLabel.WORK_TOOLS,
    "asana.com": DomainCategoryLabel.WORK_TOOLS,
    "trello.com": DomainCategoryLabel.WORK_TOOLS,
    "npmjs.com": DomainCategoryLabel.WORK_TOOLS,
    "pypi.org": DomainCategoryLabel.WORK_TOOLS,
    "stackoverflow.com": DomainCategoryLabel.WORK_TOOLS,
    "azure.com": DomainCategoryLabel.WORK_TOOLS,
    "digitalocean.com": DomainCategoryLabel.WORK_TOOLS,
}

_GAMBLING_TLDS = (".bet", ".casino", ".poker")
# .xxx is a real, IANA-registered gTLD reserved for adult content -- a much
# stronger signal than any keyword, so it's checked the same way as the
# gambling TLDs above (before the weaker keyword tier).
_ADULT_CONTENT_TLDS = (".xxx",)

_KEYWORD_HINTS: tuple[tuple[str, DomainCategoryLabel], ...] = (
    ("gambl", DomainCategoryLabel.GAMBLING),
    ("casino", DomainCategoryLabel.GAMBLING),
    ("poker", DomainCategoryLabel.GAMBLING),
    ("porn", DomainCategoryLabel.ADULT_CONTENT),
    ("xxx", DomainCategoryLabel.ADULT_CONTENT),
    ("adult", DomainCategoryLabel.ADULT_CONTENT),
    ("music", DomainCategoryLabel.MUSIC_STREAMING),
    ("game", DomainCategoryLabel.GAMING),
    ("stream", DomainCategoryLabel.VIDEO_STREAMING),
    ("video", DomainCategoryLabel.VIDEO_STREAMING),
    ("social", DomainCategoryLabel.SOCIAL_MEDIA),
    ("shop", DomainCategoryLabel.SHOPPING),
    ("store", DomainCategoryLabel.SHOPPING),
    ("news", DomainCategoryLabel.NEWS),
)


# aggregator.py calls effective_category() (which falls back to this) once
# per raw log event, not once per unique domain -- and real traffic is
# heavily skewed toward a handful of repeat domains, so caching turns most
# calls into an O(1) lookup instead of re-scanning every hostname/keyword
# tier. Bounded so a flood of unique/attacker-controlled domains (e.g. DGA
# traffic) can't grow this unboundedly.
@lru_cache(maxsize=4096)
def infer_category(domain: str | None) -> DomainCategoryLabel:
    if not domain:
        return DomainCategoryLabel.UNCATEGORIZED
    domain = domain.lower()

    best_match_len = -1
    best_category = DomainCategoryLabel.UNCATEGORIZED
    for hostname, category in _KNOWN_HOSTNAMES.items():
        if (domain == hostname or domain.endswith("." + hostname)) and len(hostname) > best_match_len:
            best_match_len = len(hostname)
            best_category = category
    if best_match_len >= 0:
        return best_category

    if domain.endswith(_GAMBLING_TLDS):
        return DomainCategoryLabel.GAMBLING
    if domain.endswith(_ADULT_CONTENT_TLDS):
        return DomainCategoryLabel.ADULT_CONTENT

    for keyword, category in _KEYWORD_HINTS:
        if keyword in domain:
            return category

    return DomainCategoryLabel.UNCATEGORIZED


def effective_category(domain: str, overrides: dict[str, DomainCategoryLabel]) -> DomainCategoryLabel:
    """An admin-assigned category (see domain_category_service.get_overrides_map
    for how `overrides` is loaded) always wins; anything not explicitly
    categorized falls back to infer_category() rather than a bare
    "uncategorized". The single place both stats_service.py and
    time_spent_service.py resolve "what category is this domain, right now"
    through, so the two can never disagree."""
    return overrides.get(domain) or infer_category(domain)
