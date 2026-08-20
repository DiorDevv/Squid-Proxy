"""Best-effort automatic domain categorization.

This is a *default*, not an override: app/services/domain_category_service.py's
admin-assigned categories always take precedence (see get_effective_category
in stats_service.py, the only caller that combines the two). Without this,
a real deployment with hundreds of distinct domains would start with
everything dumped in "uncategorized" until an admin manually tags each one,
which doesn't scale -- this exists purely to make that starting point useful.

Four tiers, checked in order, first match wins:
  1. Known hostnames (longest suffix match, so "aws.amazon.com" resolves to
     work_tools even though the shorter "amazon.com" suffix matches shopping)
  2. UT1 bulk blacklist (see ut1_blacklist.py) -- optional, off unless
     UT1_ENABLED and a successful refresh has happened; covers millions of
     domains the ~90-entry list above never could, at the cost of being a
     bulk/automated source rather than hand-curated
  3. Category-indicating TLDs (weaker signal, but reliable for a handful of
     categories where the TLD itself is a strong hint, e.g. gambling sites
     disproportionately use .bet/.casino/.poker)
  4. Keyword substrings in the hostname itself (weakest signal -- catches
     descriptive names a known-hostname list will never cover, at the cost
     of occasional false positives)

Never raises and never returns anything but a valid DomainCategoryLabel;
an unrecognized domain is simply UNCATEGORIZED, the same as if an admin
hadn't gotten to it yet.
"""

from functools import lru_cache

from app.models.domain_category import DomainCategoryLabel
from app.services.ut1_blacklist import Ut1Blacklist

# Set by Ut1BlacklistScheduler after each successful refresh (see
# ut1_scheduler.py); None until the first refresh ever succeeds, e.g.
# UT1_ENABLED=false (the default) or the very first download hasn't
# completed yet. infer_category() below treats None as "tier absent",
# not as an error.
_ut1_blacklist: Ut1Blacklist | None = None


def set_ut1_blacklist(blacklist: Ut1Blacklist | None) -> None:
    global _ut1_blacklist
    _ut1_blacklist = blacklist
    # Domains already cached under the old (or no) blacklist may resolve
    # differently now -- e.g. UNCATEGORIZED because no blacklist was loaded
    # yet at the time, now correctly categorized. Without this, a domain
    # looked up once before the first successful refresh would stay wrong
    # in cache for the life of the process.
    infer_category.cache_clear()

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
    "rutube.ru": DomainCategoryLabel.VIDEO_STREAMING,
    "ivi.ru": DomainCategoryLabel.VIDEO_STREAMING,
    "okko.tv": DomainCategoryLabel.VIDEO_STREAMING,
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
    "ok.ru": DomainCategoryLabel.SOCIAL_MEDIA,
    "odnoklassniki.ru": DomainCategoryLabel.SOCIAL_MEDIA,
    # --- Shopping ---
    "amazon.com": DomainCategoryLabel.SHOPPING,
    "ebay.com": DomainCategoryLabel.SHOPPING,
    "aliexpress.com": DomainCategoryLabel.SHOPPING,
    "etsy.com": DomainCategoryLabel.SHOPPING,
    "walmart.com": DomainCategoryLabel.SHOPPING,
    "target.com": DomainCategoryLabel.SHOPPING,
    "wildberries.ru": DomainCategoryLabel.SHOPPING,
    "uzum.uz": DomainCategoryLabel.SHOPPING,
    "olx.uz": DomainCategoryLabel.SHOPPING,
    "avito.ru": DomainCategoryLabel.SHOPPING,
    "ozon.ru": DomainCategoryLabel.SHOPPING,
    "market.yandex.ru": DomainCategoryLabel.SHOPPING,
    # --- News ---
    "cnn.com": DomainCategoryLabel.NEWS,
    "bbc.com": DomainCategoryLabel.NEWS,
    "bbc.co.uk": DomainCategoryLabel.NEWS,
    "nytimes.com": DomainCategoryLabel.NEWS,
    "reuters.com": DomainCategoryLabel.NEWS,
    "bloomberg.com": DomainCategoryLabel.NEWS,
    "foxnews.com": DomainCategoryLabel.NEWS,
    "news.ycombinator.com": DomainCategoryLabel.NEWS,
    "kun.uz": DomainCategoryLabel.NEWS,
    "gazeta.uz": DomainCategoryLabel.NEWS,
    "daryo.uz": DomainCategoryLabel.NEWS,
    "podrobno.uz": DomainCategoryLabel.NEWS,
    "news.yandex.ru": DomainCategoryLabel.NEWS,
    "ria.ru": DomainCategoryLabel.NEWS,
    "lenta.ru": DomainCategoryLabel.NEWS,
    "rbc.ru": DomainCategoryLabel.NEWS,
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
    "npmjs.org": DomainCategoryLabel.WORK_TOOLS,
    "pypi.org": DomainCategoryLabel.WORK_TOOLS,
    "pythonhosted.org": DomainCategoryLabel.WORK_TOOLS,
    "stackoverflow.com": DomainCategoryLabel.WORK_TOOLS,
    "azure.com": DomainCategoryLabel.WORK_TOOLS,
    "digitalocean.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: security/AV/EDR vendors (a base-domain entry here
    # covers every subdomain via the longest-suffix match above, e.g.
    # "ksn-info-geo.kaspersky-labs.com" doesn't need its own entry) ---
    "kaspersky.com": DomainCategoryLabel.WORK_TOOLS,
    "kaspersky-labs.com": DomainCategoryLabel.WORK_TOOLS,
    "cisco.com": DomainCategoryLabel.WORK_TOOLS,
    "sourcefire.com": DomainCategoryLabel.WORK_TOOLS,
    "threatgrid.com": DomainCategoryLabel.WORK_TOOLS,
    "paloaltonetworks.com": DomainCategoryLabel.WORK_TOOLS,
    "ironport.com": DomainCategoryLabel.WORK_TOOLS,
    "xforce.ibm.com": DomainCategoryLabel.WORK_TOOLS,
    "xforce.ibmcloud.com": DomainCategoryLabel.WORK_TOOLS,
    "qradar.ibmcloud.com": DomainCategoryLabel.WORK_TOOLS,
    "emergingthreats.net": DomainCategoryLabel.WORK_TOOLS,
    "emergingthreatspro.com": DomainCategoryLabel.WORK_TOOLS,
    "sicherheitstacho.eu": DomainCategoryLabel.WORK_TOOLS,
    "digicert.com": DomainCategoryLabel.WORK_TOOLS,
    "globalsign.com": DomainCategoryLabel.WORK_TOOLS,
    "sectigo.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: OS/package mirrors and dev-infra CDNs ---
    "ubuntu.com": DomainCategoryLabel.WORK_TOOLS,
    "centos.org": DomainCategoryLabel.WORK_TOOLS,
    "rockylinux.org": DomainCategoryLabel.WORK_TOOLS,
    "almalinux.org": DomainCategoryLabel.WORK_TOOLS,
    "fedoraproject.org": DomainCategoryLabel.WORK_TOOLS,
    "alpinelinux.org": DomainCategoryLabel.WORK_TOOLS,
    "launchpad.net": DomainCategoryLabel.WORK_TOOLS,
    "launchpadcontent.net": DomainCategoryLabel.WORK_TOOLS,
    "remirepo.net": DomainCategoryLabel.WORK_TOOLS,
    "rpmfind.net": DomainCategoryLabel.WORK_TOOLS,
    "nodesource.com": DomainCategoryLabel.WORK_TOOLS,
    "hashicorp.com": DomainCategoryLabel.WORK_TOOLS,
    "teleport.dev": DomainCategoryLabel.WORK_TOOLS,
    "rabbitmq.com": DomainCategoryLabel.WORK_TOOLS,
    "mongodb.org": DomainCategoryLabel.WORK_TOOLS,
    "mariadb.com": DomainCategoryLabel.WORK_TOOLS,
    "redis.io": DomainCategoryLabel.WORK_TOOLS,
    "postgresql.org": DomainCategoryLabel.WORK_TOOLS,
    "pgadmin.org": DomainCategoryLabel.WORK_TOOLS,
    "clickhouse.com": DomainCategoryLabel.WORK_TOOLS,
    "k8s.io": DomainCategoryLabel.WORK_TOOLS,
    "docker.com": DomainCategoryLabel.WORK_TOOLS,
    "docker.io": DomainCategoryLabel.WORK_TOOLS,
    "jfrog.io": DomainCategoryLabel.WORK_TOOLS,
    "jfrog.com": DomainCategoryLabel.WORK_TOOLS,
    "sonatype.com": DomainCategoryLabel.WORK_TOOLS,
    "gvt1.com": DomainCategoryLabel.WORK_TOOLS,
    "gvt2.com": DomainCategoryLabel.WORK_TOOLS,
    "gvt3.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: developer tooling / IDEs / SaaS ---
    "jetbrains.com": DomainCategoryLabel.WORK_TOOLS,
    "vsassets.io": DomainCategoryLabel.WORK_TOOLS,
    "vscode-cdn.net": DomainCategoryLabel.WORK_TOOLS,
    "vscode-unpkg.net": DomainCategoryLabel.WORK_TOOLS,
    "postman.com": DomainCategoryLabel.WORK_TOOLS,
    "getpostman.com": DomainCategoryLabel.WORK_TOOLS,
    "pstmn.io": DomainCategoryLabel.WORK_TOOLS,
    "launchdarkly.com": DomainCategoryLabel.WORK_TOOLS,
    "amplitude.com": DomainCategoryLabel.WORK_TOOLS,
    "sentry.io": DomainCategoryLabel.WORK_TOOLS,
    "grafana.com": DomainCategoryLabel.WORK_TOOLS,
    "grafana.net": DomainCategoryLabel.WORK_TOOLS,
    "grafana.org": DomainCategoryLabel.WORK_TOOLS,
    "zabbix.com": DomainCategoryLabel.WORK_TOOLS,
    "elastic.co": DomainCategoryLabel.WORK_TOOLS,
    "elasticsearch.org": DomainCategoryLabel.WORK_TOOLS,
    "githubusercontent.com": DomainCategoryLabel.WORK_TOOLS,
    "github.io": DomainCategoryLabel.WORK_TOOLS,
    "huggingface.co": DomainCategoryLabel.WORK_TOOLS,
    "hf.co": DomainCategoryLabel.WORK_TOOLS,
    "openai.com": DomainCategoryLabel.WORK_TOOLS,
    "windows.net": DomainCategoryLabel.WORK_TOOLS,
    "oracle.com": DomainCategoryLabel.WORK_TOOLS,
    "schemastore.org": DomainCategoryLabel.WORK_TOOLS,
    "scarf.sh": DomainCategoryLabel.WORK_TOOLS,
    "snapcraft.io": DomainCategoryLabel.WORK_TOOLS,
    "snapcraftcontent.com": DomainCategoryLabel.WORK_TOOLS,
    "jsdelivr.net": DomainCategoryLabel.WORK_TOOLS,
    "unpkg.com": DomainCategoryLabel.WORK_TOOLS,
    "nginx.org": DomainCategoryLabel.WORK_TOOLS,
    "winscp.net": DomainCategoryLabel.WORK_TOOLS,
    "aapanel.com": DomainCategoryLabel.WORK_TOOLS,
    "ngrok.com": DomainCategoryLabel.WORK_TOOLS,
    "ghcr.io": DomainCategoryLabel.WORK_TOOLS,
    "amazonaws.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: Atlassian/collab suites already partly listed above ---
    "atl-paas.net": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: Microsoft's sprawl of infra domains outside
    # microsoft.com itself (each a genuinely separate base domain, so no
    # single blanket entry covers them) ---
    "microsoft.com": DomainCategoryLabel.WORK_TOOLS,
    "microsoftonline.com": DomainCategoryLabel.WORK_TOOLS,
    "microsoftapp.net": DomainCategoryLabel.WORK_TOOLS,
    "windowsupdate.com": DomainCategoryLabel.WORK_TOOLS,
    "live.com": DomainCategoryLabel.WORK_TOOLS,
    "msecnd.net": DomainCategoryLabel.WORK_TOOLS,
    "azureedge.net": DomainCategoryLabel.WORK_TOOLS,
    "azurefd.net": DomainCategoryLabel.WORK_TOOLS,
    "msftconnecttest.com": DomainCategoryLabel.WORK_TOOLS,
    "msftncsi.com": DomainCategoryLabel.WORK_TOOLS,
    "monitor.azure.com": DomainCategoryLabel.WORK_TOOLS,
    "clarity.ms": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: Google infra/API domains -- deliberately not a blanket
    # "google.com" (that would also swallow www.google.com, play.google.com,
    # etc., which are ordinary consumer Google, not "work") ---
    "googleapis.com": DomainCategoryLabel.WORK_TOOLS,
    "clients6.google.com": DomainCategoryLabel.WORK_TOOLS,
    "accounts.google.com": DomainCategoryLabel.WORK_TOOLS,
    "apis.google.com": DomainCategoryLabel.WORK_TOOLS,
    "mtalk.google.com": DomainCategoryLabel.WORK_TOOLS,
    "clients1.google.com": DomainCategoryLabel.WORK_TOOLS,
    "clients2.google.com": DomainCategoryLabel.WORK_TOOLS,
    "android.clients.google.com": DomainCategoryLabel.WORK_TOOLS,
    "contacts.google.com": DomainCategoryLabel.WORK_TOOLS,
    "drive.usercontent.google.com": DomainCategoryLabel.WORK_TOOLS,
    "storage.googleapis.com": DomainCategoryLabel.WORK_TOOLS,
    "youtube.googleapis.com": DomainCategoryLabel.VIDEO_STREAMING,
    # --- Work tools: Mozilla infra ---
    "mozilla.org": DomainCategoryLabel.WORK_TOOLS,
    "mozilla.net": DomainCategoryLabel.WORK_TOOLS,
    "mozilla.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Social media: messaging API (telegram.org itself is already listed
    # above; api.telegram.org is a different base domain) ---
    "api.telegram.org": DomainCategoryLabel.SOCIAL_MEDIA,
    # --- News: MSN is a news/content portal, not a work tool ---
    "msn.com": DomainCategoryLabel.NEWS,
    # --- Other: Yandex's general consumer portal/search/ads -- specific
    # Yandex services with their own category (music.yandex.ru,
    # market.yandex.ru, news.yandex.ru) already have their own longer,
    # more specific entries above and take precedence over this. ---
    "yandex.ru": DomainCategoryLabel.OTHER,
    "yandex.uz": DomainCategoryLabel.OTHER,
    "yandex.net": DomainCategoryLabel.OTHER,
    "ya.ru": DomainCategoryLabel.OTHER,
    # --- Work tools: Uzbekistan government, banking, and education portals
    # (a base-domain entry covers every service subdomain under it) ---
    "soliq.uz": DomainCategoryLabel.WORK_TOOLS,
    "sqb.uz": DomainCategoryLabel.WORK_TOOLS,
    "sqbinsurance.uz": DomainCategoryLabel.WORK_TOOLS,
    "pochta.uz": DomainCategoryLabel.WORK_TOOLS,
    "myid.uz": DomainCategoryLabel.WORK_TOOLS,
    "devmyid.uz": DomainCategoryLabel.WORK_TOOLS,
    "e-edu.uz": DomainCategoryLabel.WORK_TOOLS,
    "edu.uz": DomainCategoryLabel.WORK_TOOLS,
    "nextedu.uz": DomainCategoryLabel.WORK_TOOLS,
    "infokredit.uz": DomainCategoryLabel.WORK_TOOLS,
    "hujjat.uz": DomainCategoryLabel.WORK_TOOLS,
    "fido.uz": DomainCategoryLabel.WORK_TOOLS,
    "mf.uz": DomainCategoryLabel.WORK_TOOLS,
    "myorg.uz": DomainCategoryLabel.WORK_TOOLS,
    "baxolash.uz": DomainCategoryLabel.WORK_TOOLS,
    "gov.uz": DomainCategoryLabel.WORK_TOOLS,
    "egov.uz": DomainCategoryLabel.WORK_TOOLS,
    "e-imzo.uz": DomainCategoryLabel.WORK_TOOLS,
    "cbu.uz": DomainCategoryLabel.WORK_TOOLS,
    "uzcard.uz": DomainCategoryLabel.WORK_TOOLS,
    "smart-office.uz": DomainCategoryLabel.WORK_TOOLS,
    "atmos.uz": DomainCategoryLabel.WORK_TOOLS,
    "agroplatforma.uz": DomainCategoryLabel.WORK_TOOLS,
    "post.uz": DomainCategoryLabel.WORK_TOOLS,
    # --- Work tools: a second real deployment's archived access.log pulled
    # in a wider, independent sample -- these are the additional
    # high-confidence domains it surfaced that the first pass missed. ---
    "bitbucket.org": DomainCategoryLabel.WORK_TOOLS,
    "segment.io": DomainCategoryLabel.WORK_TOOLS,
    "skype.com": DomainCategoryLabel.WORK_TOOLS,
    "visa.com": DomainCategoryLabel.WORK_TOOLS,
    "vllm.ai": DomainCategoryLabel.WORK_TOOLS,
    "firefox.com": DomainCategoryLabel.WORK_TOOLS,
    "debian.org": DomainCategoryLabel.WORK_TOOLS,
    "pki.goog": DomainCategoryLabel.WORK_TOOLS,
    "atomicorp.com": DomainCategoryLabel.WORK_TOOLS,
    "windows.com": DomainCategoryLabel.WORK_TOOLS,
    "novemberain.com": DomainCategoryLabel.WORK_TOOLS,
    "allroundautomations.com": DomainCategoryLabel.WORK_TOOLS,
    "ibm.com": DomainCategoryLabel.WORK_TOOLS,
    "nr-data.net": DomainCategoryLabel.WORK_TOOLS,
    "newrelic.com": DomainCategoryLabel.WORK_TOOLS,
    "norma.uz": DomainCategoryLabel.WORK_TOOLS,
    "msedge.net": DomainCategoryLabel.WORK_TOOLS,
    "lencr.org": DomainCategoryLabel.WORK_TOOLS,
    "secomtrust.net": DomainCategoryLabel.WORK_TOOLS,
    "demisto.com": DomainCategoryLabel.WORK_TOOLS,
    "gitlab.net": DomainCategoryLabel.WORK_TOOLS,
    "gitlab-static.net": DomainCategoryLabel.WORK_TOOLS,
    "apache.org": DomainCategoryLabel.WORK_TOOLS,
    "glowbyteconsulting.com": DomainCategoryLabel.WORK_TOOLS,
    "office.net": DomainCategoryLabel.WORK_TOOLS,
    "quay.io": DomainCategoryLabel.WORK_TOOLS,
    "pkg.dev": DomainCategoryLabel.WORK_TOOLS,
    "jetbrains.ai": DomainCategoryLabel.WORK_TOOLS,
    "litespeedtech.com": DomainCategoryLabel.WORK_TOOLS,
    "world-check.com": DomainCategoryLabel.WORK_TOOLS,
    "tenablesecurity.com": DomainCategoryLabel.WORK_TOOLS,
    "pythonrpa.org": DomainCategoryLabel.WORK_TOOLS,
    "getcomposer.org": DomainCategoryLabel.WORK_TOOLS,
    "sfx.ms": DomainCategoryLabel.WORK_TOOLS,
    "nodejs.org": DomainCategoryLabel.WORK_TOOLS,
    "microsoft365.com": DomainCategoryLabel.WORK_TOOLS,
    "maxmind.com": DomainCategoryLabel.WORK_TOOLS,
    "1c-bitrix.ru": DomainCategoryLabel.WORK_TOOLS,
    "dl.google.com": DomainCategoryLabel.WORK_TOOLS,
    # --- Other: ad/analytics/tracking networks and generic utility sites --
    # no category in the enum fits these better; "other" beats leaving them
    # uncategorized, since they're not actually unknown, just not one of the
    # named buckets. ---
    "bing.com": DomainCategoryLabel.OTHER,
    "ipify.org": DomainCategoryLabel.OTHER,
    "getpocket.com": DomainCategoryLabel.OTHER,
    "yastatic.net": DomainCategoryLabel.OTHER,
    "googletagmanager.com": DomainCategoryLabel.OTHER,
    "doubleclick.net": DomainCategoryLabel.OTHER,
    "googleadservices.com": DomainCategoryLabel.OTHER,
    "google-analytics.com": DomainCategoryLabel.OTHER,
    "analytics.google.com": DomainCategoryLabel.OTHER,
    "adtrafficquality.google": DomainCategoryLabel.OTHER,
    "scorecardresearch.com": DomainCategoryLabel.OTHER,
    "trustarc.com": DomainCategoryLabel.OTHER,
    "oracleinfinity.io": DomainCategoryLabel.OTHER,
    "open-meteo.com": DomainCategoryLabel.OTHER,
    "pastebin.com": DomainCategoryLabel.OTHER,
    "hastebin.com": DomainCategoryLabel.OTHER,
    "quora.com": DomainCategoryLabel.OTHER,
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

    if _ut1_blacklist is not None:
        ut1_category = _ut1_blacklist.categorize(domain)
        if ut1_category is not None:
            return ut1_category

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
