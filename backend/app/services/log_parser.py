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
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

EXPECTED_FIELD_COUNT = 10

# Squid marks "no value" fields with a literal dash.
_EMPTY = "-"

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


def _extract_domain(url: str, method: str) -> str | None:
    if not url or url == _EMPTY:
        return None
    if method == "CONNECT" or "://" not in url:
        # CONNECT / tunneled requests are logged as "host:port", no scheme.
        host = url.rsplit(":", 1)[0] if ":" in url else url
        return host or None
    hostname = urlsplit(url).hostname
    return hostname


def _validate_client_ip(raw: str, line: str) -> str | None:
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        logger.warning("Invalid client IP in log line, skipping line", extra={"line": line})
        return None


def parse_line(line: str) -> ParsedEvent | None:
    """Parse a single Squid access.log line. Never raises; returns None on failure."""
    stripped = line.strip()
    if not stripped:
        return None

    tokens = stripped.split()
    if len(tokens) != EXPECTED_FIELD_COUNT:
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
        action=action,
        status_code=status_code,
        bytes=num_bytes,
        method=method,
        url=url,
        domain=domain,
        user=user,
        hierarchy=hierarchy,
        peer=peer,
        content_type=content_type,
        blocked=blocked,
    )
