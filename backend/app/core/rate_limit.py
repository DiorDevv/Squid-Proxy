"""Rate limiting setup (brute-force protection on auth endpoints).

`get_remote_address` keys on `request.client.host` -- by default that's the
direct TCP peer, which behind a reverse proxy (nginx, in both this app's
deploy paths) is the proxy itself, collapsing per-IP throttling into one
bucket shared by every real client behind it. This is made safe to trust
via `X-Forwarded-For` instead, with two preconditions that both have to hold
together (this module doesn't need to reference or read the header itself --
uvicorn's `--proxy-headers` rewrites `request.client` before this code ever
sees the request):

1. uvicorn is started with `--proxy-headers --forwarded-allow-ips=<trusted>`
   (see backend/Dockerfile's CMD and deploy/systemd/squid-dashboard-backend.service's
   ExecStart), restricted to just the reverse proxy's own address -- an
   unrestricted `--forwarded-allow-ips` would let anyone spoof the header to
   bypass or weaponize the limiter.
2. The backend is no longer reachable except through that proxy (see
   docker-compose.yml's backend port binding to 127.0.0.1, and the systemd
   unit's own 127.0.0.1 bind) -- otherwise an attacker hitting the backend
   directly could set X-Forwarded-For to anything, defeating (1) entirely.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
