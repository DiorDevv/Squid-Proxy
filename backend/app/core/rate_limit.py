"""Rate limiting setup (brute-force protection on auth endpoints).

`get_remote_address` keys on `request.client.host` -- by default that's the
direct TCP peer, which behind a reverse proxy (nginx, in both this app's
deploy paths) is the proxy itself, collapsing per-IP throttling into one
bucket shared by every real client behind it. This is made safe to trust
via `X-Forwarded-For` instead, with two preconditions that both have to hold
together (this module doesn't need to reference or read the header itself --
uvicorn's `--proxy-headers` rewrites `request.client` before this code ever
sees the request):

1. uvicorn is started with `--proxy-headers --forwarded-allow-ips=<trusted>`,
   restricted to just the reverse proxy's own address -- an unrestricted
   `--forwarded-allow-ips` (e.g. `*`) would let anyone who can reach the
   backend at all spoof the header to bypass or weaponize the limiter.
   deploy/systemd/squid-dashboard-backend.service's ExecStart trusts only
   127.0.0.1 (nginx on the same host); docker-compose.yml's backend
   `command:` trusts only frontend_net's static IP, overriding the image's
   own safe (127.0.0.1) default in backend/Dockerfile's CMD.
2. The backend is no longer reachable except through that proxy --
   otherwise an attacker hitting the backend directly could set
   X-Forwarded-For to anything, defeating (1) entirely. The systemd path
   gets this from its own 127.0.0.1 bind; docker-compose.yml gets it from
   network segmentation (backend only shares a Docker network with
   frontend and postgres -- db-backup and demo-log-generator have no
   network path to it at all, see that file's `networks:` section). Both
   preconditions were verified together end-to-end: with only (1) fixed
   but not (2), a sibling container on the same Docker network could still
   reach the backend directly and spoof the header freely.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
