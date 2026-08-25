"""Parses Squid access.log lines into structured events.

Expected native Squid logformat (space-separated, 10 fields):

    %ts.%03tu  %6tr  %>a  %Ss/%03>Hs  %<st  %rm  %ru  %[un  %Sh/%<A  %mt

Example:
    1737100800.123  45  10.0.0.5  TCP_MISS/200  1024  GET
    http://example.com/  alice  HIER_DIRECT/93.184.216.34  text/html

Malformed lines must never raise: unparseable lines are logged at WARNING
and skipped (return None) so the tailer can keep processing the stream.
"""

import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.core.config import DEFAULT_BRANCH

logger = logging.getLogger(__name__)

EXPECTED_FIELD_COUNT = 10

# Squid marks "no value" fields with a literal dash.
_EMPTY = "-"

# Mirror RawEvent's column lengths (app/models/raw_event.py) so a field that
# doesn't fit is truncated here, at parse time, rather than reaching the
# INSERT and raising a VARCHAR-length violation. On Postgres that violation
# rolls back the whole aggregator flush transaction; since _last_flushed_id
# only advances after a successful commit (by design, to avoid data loss),
# an untruncated oversized field -- e.g. a client-requested URL with a long
# hostname, or a long Content-Type from an origin server -- would otherwise
# make every flush attempt reprocess and fail on the same event forever,
# wedging aggregation for the whole instance. SQLite doesn't enforce VARCHAR
# length, so this was invisible in dev/demo and only bit the Postgres path.
_MAX_ACTION_LEN = 64
_MAX_METHOD_LEN = 16
_MAX_DOMAIN_LEN = 255
_MAX_USER_LEN = 255
_MAX_HIERARCHY_LEN = 64
_MAX_PEER_LEN = 64
_MAX_CONTENT_TYPE_LEN = 128


def _truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[:max_len]


def _truncate_opt(value: str | None, max_len: int) -> str | None:
    return None if value is None else _truncate(value, max_len)

_DENIED_PREFIXES = ("TCP_DENIED", "TCP_DENIED_REPLY")


@dataclass(slots=True, frozen=True)
class ParsedEvent:
    timestamp: datetime
    duration_ms: int
    client_ip: str
    action: str
    status_code: int
    bytes: int
    method: str
    url: str
    domain: str | None
    user: str | None
    hierarchy: str | None
    peer: str | None
    content_type: str | None
    blocked: bool
    # Which configured log source (branch/site) this event came from -- set
    # by the caller (LogTailer knows its own configured branch; the parser
    # itself has no notion of "which file" and just forwards this through.
    branch: str


def _parse_int(raw: str, field_name: str, line: str) -> int:
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Non-numeric %s field, defaulting to 0",
            field_name,
            extra={"field": field_name, "raw_value": raw, "line": line},
        )
        return 0


# A real hostname or IP literal only ever uses these characters (brackets
# for an IPv6 literal, colon for an IPv6 literal or a CONNECT "host:port"
# that a caller hasn't stripped the port from yet). Squid logs whatever a
# client sent verbatim, including non-HTTP/malformed CONNECT traffic (a
# misbehaving client, a portscan, raw bytes from a non-Squid-aware protocol)
# -- without this, that garbage becomes a "domain" indistinguishable from a
# real one, polluting every domain-based stat, category, and report.
_HOST_CHARS_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.\-:_\[\]]*[A-Za-z0-9\]])?$")


def _looks_like_host(value: str) -> bool:
    # Length is deliberately not checked here -- an overlong but otherwise
    # legitimate hostname is _truncate_opt()'s job downstream, not a reason
    # to drop the domain outright.
    return _HOST_CHARS_RE.match(value) is not None


def _extract_domain(url: str, method: str) -> str | None:
    if not url or url == _EMPTY:
        return None
    host: str | None
    if method == "CONNECT" or "://" not in url:
        # CONNECT / tunneled requests are logged as "host:port", no scheme.
        host = url.rsplit(":", 1)[0] if ":" in url else url
    else:
        try:
            host = urlsplit(url).hostname
        except ValueError:
            # urlsplit() raises on malformed authority components (e.g. an
            # unbalanced IPv6 bracket) -- Squid logs the client's requested
            # URL verbatim, so a malformed one is client-controlled input,
            # not something we can assume is well-formed. Same "never raise"
            # contract as every other field here: treat it as "no domain",
            # not a crash.
            host = None

    if not host or not _looks_like_host(host):
        return None
    return host


def _validate_client_ip(raw: str, line: str) -> str | None:
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        logger.warning("Invalid client IP in log line, skipping line", extra={"line": line})
        return None


def _looks_like_valid_prefix(tokens: list[str]) -> bool:
    """Sanity-checks the two fields Squid always logs in a rigid "TAG/value"
    shape (%Ss/%03>Hs action/status, %Sh/%<A hierarchy/peer) -- used only to
    decide whether an unexpected token count is safe to reinterpret as a
    content-type value containing whitespace, rather than actual corruption
    in an earlier field that happens to whitespace-split the same way (see
    parse_line). Not a general field validator: this project's ordinary
    tolerance for a missing "/" in these fields (see below) still applies
    once a line passes this gate and reaches the real per-field parsing."""
    action_status, hierarchy_from = tokens[3], tokens[8]
    return "/" in action_status and ("/" in hierarchy_from or hierarchy_from == _EMPTY)


def parse_line(line: str, branch: str = DEFAULT_BRANCH) -> ParsedEvent | None:
    """Parse a single Squid access.log line. Never raises; returns None on failure."""
    stripped = line.strip()
    if not stripped:
        return None

    tokens = stripped.split()
    if len(tokens) != EXPECTED_FIELD_COUNT:
        # Not the expected shape under a plain split. The most common real
        # cause is a content-type value with an embedded space (e.g. "text/
        # html; charset=UTF-8", which real servers do send) -- but that's
        # indistinguishable at the token-count level alone from actual
        # corruption earlier in the line (e.g. a raw control byte in a
        # malformed URL, which whitespace-splits the exact same way). Retry
        # with the split capped so only the last field can absorb extra
        # whitespace, then require the two fields with a rigid,
        # Squid-guaranteed "TAG/value" shape (action/status, hierarchy/peer)
        # to still look intact under that reading -- if either doesn't, the
        # excess token(s) came from corruption earlier in the line shifting
        # everything after it, not a multi-word content type, and this line
        # is rejected exactly as it always was rather than silently turned
        # into a garbled event with the wrong fields in the wrong places.
        lenient_tokens = stripped.split(maxsplit=EXPECTED_FIELD_COUNT - 1)
        if len(lenient_tokens) == EXPECTED_FIELD_COUNT and _looks_like_valid_prefix(lenient_tokens):
            tokens = lenient_tokens
        else:
            logger.warning(
                "Log line has %d fields, expected %d, skipping",
                len(tokens),
                EXPECTED_FIELD_COUNT,
                extra={"line": stripped},
            )
            return None

    (
        raw_ts,
        raw_duration,
        raw_client_ip,
        raw_action_status,
        raw_bytes,
        raw_method,
        raw_url,
        raw_user,
        raw_hierarchy_from,
        raw_content_type,
    ) = tokens

    try:
        timestamp = datetime.fromtimestamp(float(raw_ts), tz=UTC)
    except (ValueError, OverflowError, OSError):
        logger.warning("Invalid timestamp field, skipping line", extra={"line": stripped})
        return None

    client_ip = _validate_client_ip(raw_client_ip, stripped)
    if client_ip is None:
        return None

    duration_ms = _parse_int(raw_duration, "duration", stripped)
    num_bytes = _parse_int(raw_bytes, "bytes", stripped)

    if "/" in raw_action_status:
        action, raw_status = raw_action_status.split("/", 1)
    else:
        action, raw_status = raw_action_status, "0"
    status_code = _parse_int(raw_status, "status_code", stripped)

    method = raw_method
    url = raw_url
    domain = _extract_domain(url, method)

    user = None if raw_user == _EMPTY else raw_user

    hierarchy: str | None
    peer: str | None
    if "/" in raw_hierarchy_from:
        hierarchy, peer = raw_hierarchy_from.split("/", 1)
    else:
        hierarchy, peer = raw_hierarchy_from, None
    hierarchy = None if hierarchy == _EMPTY else hierarchy
    peer = None if peer in (None, _EMPTY) else peer

    content_type = None if raw_content_type == _EMPTY else raw_content_type

    blocked = action.startswith(_DENIED_PREFIXES) or status_code in (403, 407)

    return ParsedEvent(
        timestamp=timestamp,
        duration_ms=duration_ms,
        client_ip=client_ip,
        action=_truncate(action, _MAX_ACTION_LEN),
        status_code=status_code,
        bytes=num_bytes,
        method=_truncate(method, _MAX_METHOD_LEN),
        url=url,
        domain=_truncate_opt(domain, _MAX_DOMAIN_LEN),
        user=_truncate_opt(user, _MAX_USER_LEN),
        hierarchy=_truncate_opt(hierarchy, _MAX_HIERARCHY_LEN),
        peer=_truncate_opt(peer, _MAX_PEER_LEN),
        content_type=_truncate_opt(content_type, _MAX_CONTENT_TYPE_LEN),
        blocked=blocked,
        branch=branch,
    )
