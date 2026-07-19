#!/usr/bin/env python3
"""Synthetic Squid access.log generator for local development and demos.

Not part of the production backend -- deliberately has zero dependency on
the rest of the app beyond matching log_parser.py's expected line format,
so it can run standalone against any target path:

    python scripts/generate_demo_log.py --output /tmp/access.log --rate 30

Traffic shape matches the numbers from the product brief: ~20-40 req/s on
average, with periodic bursts to 200+/s. A small fraction of lines are
intentionally malformed to exercise the parser's error-tolerance path live.
"""

import argparse
import random
import time
from datetime import UTC, datetime

ALLOWED_DOMAINS = [
    "docs.internal-wiki.com",
    "mail.company.com",
    "github.com",
    "stackoverflow.com",
    "npmjs.com",
    "pypi.org",
    "aws.amazon.com",
    "cloud.google.com",
    "slack.com",
    "zoom.us",
    "wikipedia.org",
    "news.ycombinator.com",
]

BLOCKED_DOMAINS = [
    "totally-not-malware.ru",
    "free-crypto-miner.top",
    "streaming-pirate.tv",
    "adult-content-site.xxx",
    "gambling-paradise.bet",
    "social-media-timesink.com",
]

CLIENTS = [
    ("10.20.1.11", "alice"),
    ("10.20.1.12", "bob"),
    ("10.20.1.13", "carol"),
    ("10.20.1.14", "dave"),
    ("10.20.2.20", None),
    ("2001:db8:1::42", "erin"),
    ("10.20.3.31", "frank"),
    ("10.20.3.32", "grace"),
]

METHODS = ["GET", "GET", "GET", "POST", "HEAD"]
CONTENT_TYPES = ["text/html", "application/json", "image/png", "text/css", "application/javascript"]
HIERARCHIES = ["HIER_DIRECT", "HIER_DIRECT", "HIER_DIRECT", "HIER_NONE"]

# Static samples that never parse into an event at all (wrong field count /
# unparseable), so a hardcoded timestamp is harmless -- they never reach
# the point of being turned into a ParsedEvent.
_STATIC_MALFORMED_SAMPLES = [
    "",
    "this line is not a valid squid log entry at all",
]


def _random_peer_ip() -> str:
    octets = (random.randint(1, 223), random.randint(0, 255), random.randint(0, 255), random.randint(1, 254))
    return ".".join(str(o) for o in octets)


def make_line() -> str:
    now = datetime.now(UTC).timestamp()
    duration_ms = random.randint(2, 800)
    client_ip, user = random.choice(CLIENTS)
    method = random.choice(METHODS)

    is_blocked = random.random() < 0.15
    if is_blocked:
        domain = random.choice(BLOCKED_DOMAINS)
        action, status = "TCP_DENIED", 403
        num_bytes = 0
        hierarchy = "HIER_NONE"
        peer = "-"
        content_type = "-"
    else:
        domain = random.choice(ALLOWED_DOMAINS)
        action, status = "TCP_MISS", 200
        num_bytes = random.randint(200, 500_000)
        hierarchy = random.choice(HIERARCHIES)
        peer = _random_peer_ip()
        content_type = random.choice(CONTENT_TYPES)

    if random.random() < 0.03:
        method = "CONNECT"
        url = f"{domain}:443"
        content_type = "-"
    else:
        path = random.choice(["/", "/index.html", "/api/v1/data", "/assets/app.js", "/search?q=demo"])
        url = f"http://{domain}{path}"

    user_field = user if user else "-"

    return (
        f"{now:.3f} {duration_ms} {client_ip} {action}/{status} {num_bytes} "
        f"{method} {url} {user_field} {hierarchy}/{peer} {content_type}\n"
    )


def make_malformed_line() -> str:
    # The "bad numeric field" sample actually parses successfully (invalid
    # duration/bytes just default to 0, see log_parser._parse_int) -- that's
    # the exact resilience path it's meant to exercise. It must still carry
    # a *current* timestamp, though: a hardcoded historical one would parse
    # into a real ParsedEvent dated whenever this was written, which
    # poisons any window_start = min(event timestamps) calculation for
    # every flush that happens to include it (see app/insights/anomaly.py).
    now = datetime.now(UTC).timestamp()
    dynamic_samples = [
        f"{now:.3f} NOTANUMBER 10.0.0.1 TCP_MISS/200 -- GET http://example.com/ - HIER_DIRECT/1.2.3.4 -",
        f"{now:.3f} 45 999.999.999.999 TCP_MISS/200 100 GET http://example.com/ - HIER_DIRECT/1.2.3.4 -",
    ]
    samples = _STATIC_MALFORMED_SAMPLES + dynamic_samples
    return random.choice(samples) + "\n"


def run(output_path: str, avg_rate: float, malformed_rate: float, duration_seconds: float | None) -> None:
    print(f"Writing synthetic Squid access.log lines to {output_path} at ~{avg_rate}/s")
    print("Press Ctrl+C to stop.")

    started_at = time.monotonic()
    burst_until = 0.0

    with open(output_path, "a", encoding="utf-8") as f:
        while duration_seconds is None or (time.monotonic() - started_at) < duration_seconds:
            tick_start = time.monotonic()

            if tick_start > burst_until and random.random() < 0.02:
                burst_until = tick_start + random.uniform(2, 6)
                print(f"[burst] traffic spike for {burst_until - tick_start:.1f}s")

            current_rate = random.uniform(150, 250) if tick_start < burst_until else random.uniform(
                avg_rate * 0.6, avg_rate * 1.4
            )
            lines_this_tick = max(1, int(current_rate / 10))  # ticks run ~10x/sec

            for _ in range(lines_this_tick):
                if random.random() < malformed_rate:
                    f.write(make_malformed_line())
                else:
                    f.write(make_line())
            f.flush()

            elapsed = time.monotonic() - tick_start
            time.sleep(max(0.0, 0.1 - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="./access.log", help="Path to write log lines to (appended).")
    parser.add_argument("--rate", type=float, default=30.0, help="Average lines per second.")
    parser.add_argument(
        "--malformed-rate",
        type=float,
        default=0.01,
        help="Fraction of lines that are intentionally malformed.",
    )
    parser.add_argument(
        "--duration", type=float, default=None, help="Stop after this many seconds (default: run forever)."
    )
    args = parser.parse_args()

    try:
        run(args.output, args.rate, args.malformed_rate, args.duration)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
