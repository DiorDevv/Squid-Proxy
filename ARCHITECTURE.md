# Architecture

This document explains the *why* behind the non-obvious decisions in this codebase. For *what*
lives where, see the READMEs and the code itself.

## Two-tier read model: ring buffer vs. database

The backend keeps a bounded in-memory ring buffer (`app/services/event_store.py`,
`deque(maxlen=RING_BUFFER_MAX_EVENTS)`) of the most recently parsed events, alongside a database
that accumulates per-minute aggregates and (separately) raw per-event rows.

**Every bucketed/statistical endpoint (`/api/summary`, `/api/timeseries`, `/api/top-domains`,
`/api/top-blocked`, `/api/clients`) always reads from the database, never the ring buffer** — even
for a 1-hour range. The alternative (serve small ranges from memory, large ranges from the
database) was rejected: it would mean two code paths could disagree on the same number depending
on which range a user picked, which is unacceptable for a compliance tool where the numbers need
to be trustworthy. A single source of truth for aggregates, always the database, avoids that
class of bug entirely.

The ring buffer exists purely to serve `/ws/live` and `/api/events/recent` fast, and to give the
aggregator (see below) something to consume. It is not a cache of the database — it is upstream
of it.

## Ring buffer → aggregator → database

Every 60 seconds (`AGGREGATION_INTERVAL_SECONDS`), `app/services/aggregator.py` pulls everything
appended to the ring buffer since its last run (`RingBuffer.events_since(last_id)`, tracked by a
monotonically increasing id) and, in one transaction:

- increments per-minute global totals (`minute_aggregates`)
- increments per-minute per-domain counts (`domain_minute_aggregates`)
- increments per-minute per-client counts (`client_minute_aggregates`)
- inserts full-detail rows into `raw_events`

Aggregation and raw storage happen from the *same* flush pass over the *same* events, so they can
never drift apart. Rows are upserted (select-then-increment, not a dialect-specific
`ON CONFLICT`) to keep the code portable across SQLite and Postgres without maintaining two
implementations.

## Why persist raw events at all, separately from aggregates

A per-minute aggregate can answer "how much traffic," but not "what did client X actually
request at 14:32:07" — and a security/compliance dashboard needs the latter for
`/api/clients/{id}/activity` and `/api/export`, for ranges beyond whatever currently fits in the
in-memory ring buffer. `raw_events` is the durable, queryable source for that, with its own
(shorter) retention window (`RETENTION_DAYS_RAW_EVENTS`, default 7 days) independent of
`RETENTION_DAYS_AGGREGATES` (default ~400 days) — aggregates are cheap to keep for long-term
trend reporting; full per-event detail is comparatively expensive to retain indefinitely, so the
two are allowed to age out on different schedules (`app/services/retention.py`).

## Ring buffer sizing is a real capacity tradeoff, not just a config default

At the traffic volumes in the brief (1-3M requests/day, bursts to 200+/s), holding a literal 24
hours of raw events in memory would be several hundred MB to >1GB depending on record size.
`RING_BUFFER_MAX_EVENTS` defaults to a smaller, safer window and is meant to be tuned to the
deployment's actual RAM budget — `raw_events` in the database is the real long-window source of
truth for detail queries, so a conservative in-memory window doesn't lose data, it just changes
where a detail query is served from.

## WebSocket + REST polling fallback, not WebSocket-only

`/ws/live` pushes new events immediately, but the frontend is built so **every feature works over
plain REST polling** if the socket can't connect (corporate proxies, load balancers that don't
support upgrade, transient network issues) — this is a monitoring tool for a security team; it
must not go blind just because a WebSocket handshake failed. `useWebSocket` reconnects with
capped exponential backoff; whenever it isn't in the `open` state, TanStack Query's
`refetchInterval` polls `/api/events/recent` every 10s instead. The connection-status dot in the
topbar reflects this honestly (green = live, gray = polling, red = REST itself is failing too).

## Auth: short-lived access token in memory, refresh token in an httpOnly cookie

- Access tokens (JWT, 15–30 min) are returned in the login response body and held **only** in a
  Zustand store on the frontend — never `localStorage` — to limit what an XSS payload could
  exfiltrate. The tradeoff is that a hard page reload loses the token; `App.tsx` calls
  `POST /api/auth/refresh` once on mount to silently re-establish the session from the cookie.
- Refresh tokens are opaque (`jti` + random secret, not a JWT), stored server-side hashed
  (`refresh_tokens` table) and delivered as an `httpOnly`, `Secure` (in production),
  `SameSite=Strict` cookie scoped to `/api/auth`. Every refresh **rotates** the token — the old
  one is marked revoked — so a replayed/stolen refresh token is both detectable and only useful
  once.
- `/api/auth/refresh` intentionally does not return the user's email (only a new access token),
  since the refresh token cookie doesn't carry it; the frontend recovers the *role* by decoding
  the (unverified, display-only) JWT payload client-side — the backend independently verifies the
  role on every request regardless of what the client believes.

## WebSocket authentication via a single-use ticket, not the access token

Browsers cannot attach an `Authorization` header to a WebSocket handshake. Rather than put the
long-lived access token in the `/ws/live` URL (where it could leak into proxy/server access
logs), the frontend first calls `POST /api/auth/ws-ticket` (a normal authenticated REST call),
gets back a ticket good for ~30 seconds and one use, and passes *that* as a query param instead.
The ticket store (`app/core/security.py:WsTicketStore`) is in-memory and single-process by
design, matching the ring buffer's scaling envelope — a multi-instance deployment would need a
shared store (e.g. Redis) for this to keep working, which is a reasonable place to grow the
system later rather than something worth the complexity now.

## SQLite by default, Postgres via one environment variable

`DATABASE_URL`'s scheme alone picks the async driver (`sqlite+aiosqlite://` vs.
`postgresql+asyncpg://`); nothing else in the code branches on which database is in use. This
means `uvicorn app.main:app` works with zero external services for local development (SQLite,
with `PRAGMA journal_mode=WAL` for concurrent reads while the aggregator writes), while
`docker-compose.yml` points at a bundled Postgres for anything beyond a laptop. Schema is created
automatically on startup (`init_db()`); an Alembic baseline migration is also included for teams
that want explicit, reviewed migrations going forward.

## Log tailer: rotation-safe, never crashes the process

`app/services/log_tailer.py` polls the log file's `stat()` on a fixed interval rather than using
inotify, trading a little latency (default 0.75s) for portability and simplicity. It handles both
common `logrotate` strategies:

- **create mode** (file renamed/removed, new file created at the same path): detected via inode
  change; any bytes already written to the old, now-detached file descriptor are drained and
  parsed before switching to the new file.
- **copytruncate mode** (file truncated in place): detected via `size < last-read-offset` with an
  unchanged inode; the tailer seeks back to 0.

If the file is briefly missing (e.g. mid-rotation race), the tailer retries with exponential
backoff (capped at `LOG_TAILER_BACKOFF_MAX_SECONDS`) instead of crashing, and reports its
liveness via `/api/health` so monitoring can alert if it stays down. Malformed lines are logged
and skipped by `log_parser.py` — a single bad line never takes down the tailer or the line after
it.

## `insights/` — an intentionally empty extension point

The product brief is explicit that an AI-generated insights/anomaly-detection layer is planned
but **not** to be built now. `app/insights/base.py` defines the interface such a layer would
implement (`InsightsProvider.analyze_window()` / `.detect_anomalies()`), `app/insights/noop.py`
is the only implementation today (returns nothing), and a config-driven factory
(`INSIGHTS_PROVIDER=noop`) is the single place a future real implementation would be swapped in.
No routes or UI reference this module — it exists purely so that building the real thing later is
additive, not a refactor.

## Frontend design commitments

The dashboard commits to a single dark "Network Operations Center" theme rather than a
light/dark toggle — this is an internal security tool, not a consumer product, and the brief is
explicit that it should read as a dense, technical instrument. One accent color (amber) carries
all warning/blocked/primary-action semantics; emerald is reserved for healthy/allowed state; red
is reserved for actual failures (a disconnected backend), so it stays meaningful when it
appears. All numeric/IP/timestamp values render in a monospace font (JetBrains Mono) site-wide so
columns of numbers stay visually aligned and read as "data" rather than prose.

## Testing strategy

Backend tests exercise real code paths against a real (in-memory SQLite, `StaticPool`) database
rather than mocking the ORM — including the aggregator's actual `flush()` upsert logic, not just
hand-inserted rows, since that upsert path is where a real bug (freshly-constructed SQLAlchemy
rows have `None` counters until first flush, so `row.total += n` raised on every new bucket) was
caught during manual end-to-end QA and only then back-filled with a regression test
(`tests/test_aggregator.py`). The lesson generalized into a project convention: any service that
writes through the ORM gets at least one test that exercises the real write path, not just a
query built on pre-seeded fixture rows.
