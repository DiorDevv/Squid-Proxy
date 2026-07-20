"""Rate limiting setup (brute-force protection on auth endpoints).

`get_remote_address` keys on the direct TCP peer, not `X-Forwarded-For` --
correct default (an internet-facing backend would let anyone spoof that
header to bypass or weaponize the limiter). The tradeoff: docker-compose.yml
puts nginx in front of the backend, so in that deployment every request's
direct peer is the nginx container, and per-IP login throttling collapses
into one limit shared by every real client behind it. Trusting
X-Forwarded-For safely needs uvicorn's `--forwarded-allow-ips` restricted to
just the reverse proxy's address *and* the backend's own port no longer
reachable directly (docker-compose.yml currently publishes it on the host)
-- a deployment-topology change, not something to flip on quietly here.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
