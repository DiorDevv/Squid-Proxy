"""Bulk domain categorization sourced from UT1 (Universite Toulouse Capitole)
-- a free, categorized domain blacklist built for exactly this use case
(school/enterprise content filtering), updated roughly daily upstream. See
https://dsi.ut-capitole.fr/blacklists/ .

This supplements, never replaces, category_inference.py's existing tiers:
the ~90-entry curated _KNOWN_HOSTNAMES list stays checked first (it encodes
deliberate, precise distinctions like "aws.amazon.com is work_tools even
though amazon.com is shopping" that a bulk list has no notion of), then this,
then the weaker TLD/keyword tiers as a last resort.

Only a handful of UT1's ~68 categories map cleanly onto this app's
DomainCategoryLabel enum (see _UT1_CATEGORY_MAP below) -- the rest (malware,
phishing, vpn, webmail, dating, ...) either have no matching label or would
force content into a category it doesn't really belong to, so they're never
downloaded at all: no benefit, just wasted memory/disk.

Memory footprint is the reason this isn't just "load every line into a
set[str]": UT1's adult/domains alone is ~4.6M lines, and a plain
frozenset[str] of that measured ~570MB resident. Storing a 64-bit hash of
each domain in a sorted array.array('Q') instead cuts that to ~35MB (an
array of 8-byte ints has no per-string Python object overhead), with lookup
via bisect. The tradeoff is a vanishingly small false-positive rate from
hash collisions (~6e-7 for the largest category, by the birthday bound) --
acceptable here the same way the existing keyword-substring tier already
tolerates false positives; there's no false-negative risk, and nothing
about this feature is a security control, just a categorization label.
"""

import array
import bisect
import logging
import os
import tarfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from app.models.domain_category import DomainCategoryLabel

logger = logging.getLogger(__name__)

# UT1 folder name -> this app's label. Only categories both worth loading
# (would actually populate a label real deployments filter/report on) and
# clean (unambiguous fit, not "sort of adjacent") are included -- see the
# module docstring for why the rest of UT1's ~68 categories are skipped.
# "arjel" is the French gambling regulator's list of licensed operators --
# still gambling *content*, regardless of legality, so it maps the same as
# "gambling" itself.
_UT1_CATEGORY_MAP: dict[str, DomainCategoryLabel] = {
    "adult": DomainCategoryLabel.ADULT_CONTENT,
    "gambling": DomainCategoryLabel.GAMBLING,
    "arjel": DomainCategoryLabel.GAMBLING,
    "games": DomainCategoryLabel.GAMING,
    "social_networks": DomainCategoryLabel.SOCIAL_MEDIA,
    "shopping": DomainCategoryLabel.SHOPPING,
    "press": DomainCategoryLabel.NEWS,
    "audio-video": DomainCategoryLabel.VIDEO_STREAMING,
    # UT1 also has a dedicated "radio" folder (internet radio stations --
    # audio only) -- mapped separately from "audio-video" so this app's
    # music_streaming label actually gets populated by UT1 at all, not just
    # the curated list. Without this, ~12% of "audio-video" itself (radio/
    # music stations mixed into that folder upstream) would still land in
    # video_streaming instead, since audio-video was checked first.
    "radio": DomainCategoryLabel.MUSIC_STREAMING,
}

# Checked in this fixed order so results are deterministic on the rare
# occasion a domain ends up filed under more than one mapped UT1 category.
_LABEL_CHECK_ORDER: tuple[DomainCategoryLabel, ...] = (
    DomainCategoryLabel.ADULT_CONTENT,
    DomainCategoryLabel.GAMBLING,
    DomainCategoryLabel.GAMING,
    DomainCategoryLabel.SOCIAL_MEDIA,
    DomainCategoryLabel.MUSIC_STREAMING,
    DomainCategoryLabel.VIDEO_STREAMING,
    DomainCategoryLabel.SHOPPING,
    DomainCategoryLabel.NEWS,
)

_HASH_MASK = 0xFFFFFFFFFFFFFFFF


def _domain_hash(domain: str) -> int:
    return hash(domain) & _HASH_MASK


class CompactDomainSet:
    """A memory-lean, approximate `set[str]` of domains: stores a sorted
    array of 64-bit hashes instead of the strings themselves. See the module
    docstring for the memory/false-positive tradeoff this makes."""

    __slots__ = ("_hashes",)

    def __init__(self) -> None:
        self._hashes: array.array = array.array("Q")

    def add_lines(self, lines: Iterable[str]) -> None:
        """Streams `lines` (not read into a list first) so peak memory
        during a refresh stays bounded by the input file size, not by
        holding every domain string in memory at once alongside the hash
        array being built from them."""
        for line in lines:
            domain = line.strip()
            if domain:
                self._hashes.append(_domain_hash(domain))

    def finalize(self) -> None:
        """Sorts (and dedupes) the accumulated hashes so __contains__ can
        binary-search instead of scanning. Call once after all add_lines()
        calls for this set are done."""
        self._hashes = array.array("Q", sorted(set(self._hashes)))

    def __contains__(self, domain: str) -> bool:
        h = _domain_hash(domain)
        i = bisect.bisect_left(self._hashes, h)
        return i < len(self._hashes) and self._hashes[i] == h

    def __len__(self) -> int:
        return len(self._hashes)


def _domain_and_ancestors(domain: str) -> Iterable[str]:
    """"a.b.example.com" -> "a.b.example.com", "b.example.com",
    "example.com" -- stops at two labels (doesn't also check the bare TLD),
    matching how the existing curated-hostname tier's suffix matching works.
    No public-suffix-list awareness, same simplification that tier already
    makes."""
    labels = domain.split(".")
    for start in range(len(labels) - 1):
        yield ".".join(labels[start:])


class Ut1Blacklist:
    def __init__(self, sets_by_label: dict[DomainCategoryLabel, CompactDomainSet]) -> None:
        self._sets_by_label = sets_by_label

    def categorize(self, domain: str) -> DomainCategoryLabel | None:
        domain = domain.lower()
        candidates = list(_domain_and_ancestors(domain))
        for label in _LABEL_CHECK_ORDER:
            domain_set = self._sets_by_label.get(label)
            if domain_set is None:
                continue
            if any(candidate in domain_set for candidate in candidates):
                return label
        return None

    def stats(self) -> dict[str, int]:
        return {label.value: len(s) for label, s in self._sets_by_label.items()}


def _write_category_file_atomically(path: Path, data: bytes) -> None:
    """Write-then-rename, not a direct write to `path`: a crash or
    disk-full mid-write used to truncate a category's previously-good file
    in place, and build_from_dir() would then silently load that truncated
    file next refresh -- quietly shrinking blacklist coverage instead of
    keeping the last-good version. os.replace is atomic on POSIX, same
    pattern archive_service.py and log_tailer.py's state file already use.
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "wb") as out:
            out.write(data)
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def download_and_extract(dest_dir: Path, mirror_url: str, timeout_seconds: float = 120.0) -> None:
    """Downloads the UT1 tarball and extracts only the `domains` file of
    each category in _UT1_CATEGORY_MAP into dest_dir/<category>/domains --
    the tarball has ~68 categories and a LICENSE/README we have no use for,
    so extracting selectively saves most of the ~25MB download's disk and
    the time to inflate parts we'd never read."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_dir / ".download.tar.gz"

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client, \
            client.stream("GET", mirror_url) as response:
        response.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)

    wanted_members = {f"blacklists/{category}/domains" for category in _UT1_CATEGORY_MAP}
    with tarfile.open(tmp_path) as tar:
        for member in tar:
            if member.name not in wanted_members:
                continue
            category = member.name.split("/")[1]
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            category_dir = dest_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)
            _write_category_file_atomically(category_dir / "domains", extracted.read())

    tmp_path.unlink(missing_ok=True)


def build_from_dir(dest_dir: Path) -> Ut1Blacklist:
    """Builds a Ut1Blacklist from previously-downloaded/extracted category
    files under dest_dir (see download_and_extract). Categories with no
    extracted file yet (e.g. first run, or that category's UT1 folder was
    briefly unavailable last refresh) are silently skipped rather than
    raising -- this function must never leave the app with no blacklist at
    all just because one of several categories is temporarily missing."""
    sets_by_label: dict[DomainCategoryLabel, CompactDomainSet] = {}
    for category, label in _UT1_CATEGORY_MAP.items():
        domains_file = dest_dir / category / "domains"
        if not domains_file.exists():
            continue
        domain_set = sets_by_label.setdefault(label, CompactDomainSet())
        with open(domains_file, encoding="utf-8", errors="ignore") as f:
            domain_set.add_lines(f)

    for domain_set in sets_by_label.values():
        domain_set.finalize()

    blacklist = Ut1Blacklist(sets_by_label)
    logger.info("UT1 blacklist built", extra={"stats": blacklist.stats()})
    return blacklist


def refresh(dest_dir: Path, mirror_url: str) -> Ut1Blacklist:
    """Full refresh: download the latest tarball, extract the categories we
    use, rebuild the compact sets. Synchronous/blocking and CPU-heavy (the
    hash-building loop over ~4.6M adult/domains lines alone takes several
    seconds) -- callers on the asyncio event loop must run this via
    asyncio.to_thread, never awaited directly, or every concurrent request
    stalls for the duration."""
    download_and_extract(dest_dir, mirror_url)
    return build_from_dir(dest_dir)
