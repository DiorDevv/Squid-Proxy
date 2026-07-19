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


def test_blocked_action_sets_blocked_flag():
    line = "1737100800.123 5 10.0.0.9 TCP_DENIED/403 0 GET http://blocked-site.com/ dave HIER_NONE/- -"
    event = parse_line(line)

    assert event is not None
    assert event.blocked is True
    assert event.status_code == 403


def test_invalid_timestamp_skips_line():
    line = "not-a-timestamp 45 10.0.0.5 TCP_MISS/200 1024 GET http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    assert parse_line(line) is None
