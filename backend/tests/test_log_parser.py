from datetime import UTC, datetime

from app.services.log_parser import parse_line


def test_well_formed_line_parses_all_fields():
    line = "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/page alice HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)

    assert event is not None
    assert event.client_ip == "10.0.0.5"
    assert event.action == "TCP_MISS"
    assert event.status_code == 200
    assert event.duration_ms == 45
    assert event.bytes == 1024
    assert event.method == "GET"
    assert event.domain == "example.com"
    assert event.user == "alice"
    assert event.hierarchy == "HIER_DIRECT"
    assert event.peer == "93.184.216.34"
    assert event.content_type == "text/html"
    assert event.blocked is False


def test_empty_line_returns_none():
    assert parse_line("") is None
    assert parse_line("   \n") is None


def test_malformed_numeric_field_defaults_to_zero_but_keeps_line():
    line = "1737100800.123 NOTANUMBER 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)

    assert event is not None
    assert event.duration_ms == 0
    assert event.client_ip == "10.0.0.5"


def test_missing_user_field_is_none():
    line = "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ - HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)

    assert event is not None
    assert event.user is None


def test_connect_method_extracts_host_port_domain():
    line = "1737100800.123 12 10.0.0.7 TCP_TUNNEL/200 512 CONNECT example.com:443 bob HIER_DIRECT/93.184.216.34 -"
    event = parse_line(line)

    assert event is not None
    assert event.method == "CONNECT"
    assert event.domain == "example.com"
    assert event.content_type is None


def test_connect_with_non_hostname_garbage_yields_no_domain():
    # A non-HTTP/malformed CONNECT tunnel (a misbehaving client, raw bytes
    # from a non-Squid-aware protocol) still gets logged by Squid verbatim --
    # this must not be accepted as a "domain" just because it has no "://",
    # or it pollutes every domain-based stat/category with junk.
    line = "1737100800.123 12 10.0.0.7 TCP_TUNNEL/200 512 CONNECT %EF%BF%BD%01%02:443 bob HIER_DIRECT/93.184.216.34 -"
    event = parse_line(line)

    assert event is not None
    assert event.domain is None


def test_connect_extracts_ip_literal_domain():
    line = "1737100800.123 12 10.0.0.7 TCP_TUNNEL/200 512 CONNECT 172.25.25.40:443 bob HIER_DIRECT/93.184.216.34 -"
    event = parse_line(line)

    assert event is not None
    assert event.domain == "172.25.25.40"


def test_ipv6_client_ip_is_accepted():
    line = "1737100800.123 30 2001:db8::1 TCP_MISS/200 256 GET http://example.com/ carol HIER_DIRECT/2001:db8::2 text/plain"
    event = parse_line(line)

    assert event is not None
    assert event.client_ip == "2001:db8::1"
    assert event.peer == "2001:db8::2"


def test_invalid_client_ip_skips_line():
    line = "1737100800.123 30 not-an-ip TCP_MISS/200 256 GET http://example.com/ carol HIER_DIRECT/93.184.216.34 text/plain"
    assert parse_line(line) is None


def test_wrong_field_count_skips_line():
    assert parse_line("1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET") is None


def test_content_type_with_embedded_space_still_parses():
    # Some real servers send a Content-Type with a charset parameter (e.g.
    # "text/html; charset=UTF-8"), which Squid can log verbatim -- a naive
    # split() would see this as an 11th field and reject the whole line even
    # though every other field is well-formed.
    line = (
        "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ "
        "alice HIER_DIRECT/93.184.216.34 text/html; charset=UTF-8"
    )
    event = parse_line(line)

    assert event is not None
    assert event.content_type == "text/html; charset=UTF-8"
    assert event.client_ip == "10.0.0.5"


def test_blocked_action_sets_blocked_flag():
    line = "1737100800.123 5 10.0.0.9 TCP_DENIED/403 0 GET http://blocked-site.com/ dave HIER_NONE/- -"
    event = parse_line(line)

    assert event is not None
    assert event.blocked is True
    assert event.status_code == 403


def test_invalid_timestamp_skips_line():
    line = "not-a-timestamp 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    assert parse_line(line) is None


def test_malformed_url_authority_does_not_raise():
    # A malformed IPv6 bracket in the requested URL (client-controlled input,
    # logged verbatim by Squid) used to make urlsplit() raise ValueError
    # inside _extract_domain, breaking the "never raise" contract and wedging
    # the log tailer that reads this line. The rest of the event is still
    # valid and useful -- only the domain is unknown.
    line = "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://[::1/path alice HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)

    assert event is not None
    assert event.domain is None
    assert event.client_ip == "10.0.0.5"


def test_oversized_domain_is_truncated_to_column_length():
    # A client-requested URL with a hostname longer than RawEvent.domain's
    # String(255) column used to reach the aggregator's bulk INSERT
    # untouched; on Postgres that raises a VARCHAR-length violation that
    # rolls back the whole flush transaction, and since _last_flushed_id
    # only advances on a successful commit, the poisoned event gets retried
    # and fails identically forever, wedging aggregation instance-wide.
    long_host = "a" * 300 + ".example.com"
    line = f"1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://{long_host}/ alice HIER_DIRECT/93.184.216.34 text/html"
    event = parse_line(line)

    assert event is not None
    assert event.domain is not None
    assert len(event.domain) == 255
    assert event.domain == long_host[:255]


def test_oversized_content_type_and_user_are_truncated_to_column_length():
    long_user = "u" * 300
    long_content_type = "text/plain; charset=" + "x" * 300
    line = (
        f"1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ "
        f"{long_user} HIER_DIRECT/93.184.216.34 {long_content_type}"
    )
    event = parse_line(line)

    assert event is not None
    assert event.user is not None and len(event.user) == 255
    assert event.content_type is not None and len(event.content_type) == 128


# --- Alternate logformat: "%tl.%03tu ... %ru %Sh/%<A %[un %mt" -------------
# Some boxes in this deployment log an Apache-style local-time clock (with a
# space before the zone offset, and ".mmm" glued onto it) instead of epoch
# seconds, and put hierarchy/peer before user. parse_line() normalises both
# on the way in -- see log_parser._normalize_alt_format.


def test_alt_logformat_forward_request_parses_with_native_field_mapping():
    line = (
        "03/Sep/2026:15:22:46 +0500.112  25197 172.25.103.167 TCP_MISS/200 7369 "
        "POST http://149.154.167.41/api HIER_DIRECT/149.154.167.41 - application/octet-stream"
    )
    event = parse_line(line, branch="main")

    assert event is not None
    assert event.client_ip == "172.25.103.167"
    assert event.action == "TCP_MISS"
    assert event.status_code == 200
    assert event.duration_ms == 25197
    assert event.bytes == 7369
    assert event.method == "POST"
    assert event.domain == "149.154.167.41"
    assert event.user is None
    assert event.hierarchy == "HIER_DIRECT"
    assert event.peer == "149.154.167.41"
    assert event.content_type == "application/octet-stream"
    assert event.blocked is False
    # 03/Sep/2026 15:22:46 +05:00 == 10:22:46Z, plus .112 fractional seconds.
    assert event.timestamp == datetime(2026, 9, 3, 10, 22, 46, 112000, tzinfo=UTC)


def test_alt_logformat_connect_tunnel_extracts_domain_and_null_user():
    line = (
        "03/Sep/2026:15:22:46 +0500.233    995 172.25.42.24 TCP_TUNNEL/200 4381 "
        "CONNECT clientservices.googleapis.com:443 HIER_DIRECT/142.250.120.102 - -"
    )
    event = parse_line(line, branch="main")

    assert event is not None
    assert event.method == "CONNECT"
    assert event.domain == "clientservices.googleapis.com"
    assert event.user is None
    assert event.hierarchy == "HIER_DIRECT"
    assert event.peer == "142.250.120.102"
    assert event.content_type is None
    assert event.blocked is False


def test_alt_logformat_denied_line_sets_blocked_and_empty_peer():
    line = (
        "03/Sep/2026:15:22:46 +0500.216      0 172.25.42.77 TCP_DENIED/403 422 "
        "HEAD http://example.com/x HIER_NONE/- - text/html"
    )
    event = parse_line(line, branch="main")

    assert event is not None
    assert event.blocked is True
    assert event.status_code == 403
    assert event.hierarchy == "HIER_NONE"
    assert event.peer is None
    assert event.user is None


def test_alt_logformat_keeps_multiword_content_type_and_real_user():
    line = (
        "03/Sep/2026:15:22:46 +0500.100     10 10.0.0.1 TCP_MISS/200 5 GET "
        "http://example.com/ HIER_DIRECT/1.2.3.4 alice text/html; charset=UTF-8"
    )
    event = parse_line(line, branch="main")

    assert event is not None
    assert event.user == "alice"
    assert event.hierarchy == "HIER_DIRECT"
    assert event.peer == "1.2.3.4"
    assert event.content_type == "text/html; charset=UTF-8"


def test_alt_logformat_negative_zone_offset():
    line = (
        "03/Sep/2026:05:22:46 -0430.000     10 10.0.0.1 TCP_MISS/200 5 GET "
        "http://example.com/ HIER_DIRECT/1.2.3.4 - text/plain"
    )
    event = parse_line(line, branch="main")

    assert event is not None
    # 05:22:46 -04:30 == 09:52:46Z
    assert event.timestamp == datetime(2026, 9, 3, 9, 52, 46, tzinfo=UTC)


def test_native_epoch_line_is_untouched_by_alt_normaliser():
    # The alt-format clock regex must never fire on a native line -- field
    # order (user before hierarchy) has to stay as-is.
    line = (
        "1788430186.871 25189 172.25.55.35 TCP_MISS/200 423 POST "
        "http://149.154.167.41/api - HIER_DIRECT/149.154.167.41 application/octet-stream"
    )
    event = parse_line(line, branch="server")

    assert event is not None
    assert event.user is None
    assert event.hierarchy == "HIER_DIRECT"
    assert event.peer == "149.154.167.41"
    assert event.timestamp == datetime.fromtimestamp(1788430186.871, tz=UTC)
