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
never drift apart. Rows are upserted via one dialect-specific `INSERT ... ON CONFLICT DO UPDATE`
per table per flush (`app/services/db_upsert.py`), not select-then-increment one row at a time --
that scaled linearly with how many distinct buckets/domains/clients a flush window touches, which
grows with traffic.

**Only advance past a flush's events once they're durably committed.** `_last_flushed_id` used to
be set right after reading the events, before the transaction that actually persists them --
a failed commit (a transient DB hiccup, a bug) still marked them flushed, silently skipping that
whole window forever despite nothing having been written. Verified with a test that forces the
first commit to fail: the events must still show up in `backlog_size`, and a retry must actually
persist them.

**Building the per-bucket totals, and inserting `raw_events`, both run off the event loop.**
Bucketing (~400ms/150k events, pure dict bookkeeping + `effective_category()`) runs via
`asyncio.to_thread`, same reasoning as `log_tailer.py`'s. `raw_events` uses a Core bulk
`INSERT` of plain dicts rather than `session.add_all()` with ORM objects -- add_all()'s
identity-map bookkeeping alone measured ~960ms of synchronous CPU time for 150k rows, on top of
whatever the implicit flush inside `commit()` then also costs; switching it, verified against a
live deployment, cut the worst-case API request latency during a real 150k-line ingest burst from
~4.1s to ~0.7s (and average latency roughly 7x, since the event loop can now actually interleave
other work throughout, not just during network-wait gaps).

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
where a detail query is served from. See "Sizing for a large client count" below for a concrete
worked example of tuning this against a specific target load, not just RAM budget in the abstract.

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
`docker-compose.yml` points at a bundled Postgres for anything beyond a laptop.

Schema changes go through Alembic (`app/db/migrations/`), not just `init_db()`'s
`Base.metadata.create_all()` at startup — `create_all()` only ever creates tables that don't exist
yet, it never alters an existing one, so it can't be the whole story once a table has shipped and
needs a later column/enum change. The Docker image's entrypoint (`docker-entrypoint.sh`) and the
systemd unit (`deploy/systemd/squid-dashboard-backend.service`, via `ExecStartPre=`) both run
`alembic upgrade head` before the app starts, so this is automatic for both deploy paths; `init_db()`
still runs after that (harmless/idempotent) purely so a brand-new, empty database also works via a
plain `uvicorn app.main:app` with no separate migration step for local dev.

**Upgrading a database that predates this** (i.e. was only ever bootstrapped by `create_all()`, with
no `alembic_version` table): run `alembic stamp head` once, manually, before deploying a version that
runs `alembic upgrade head` automatically -- otherwise it tries to replay every migration from the
very first one against tables that already exist, and fails with "table already exists" on the first
one it hits. This can't be detected and handled automatically in general, since a `create_all()`-only
database's actual schema is whatever the code version running at the time produced, not a fixed,
predictable target to check against.

## Scaling to a large client count: what's handled, what isn't yet

A single-instance deployment (the only mode this app runs in today — see the next section) was
measured and hardened to hold up at a much larger client count and data volume than the original
demo scale, without changing the deployment model:

- **Aggregator writes are bulk upserts, not per-row.** `Aggregator.flush()` used to
  select-then-increment one row at a time per distinct (bucket, domain)/(bucket, client) key
  touched in a flush window — fine for a handful of domains/clients per minute, not for thousands.
  `app/services/db_upsert.py::bulk_upsert_sum` does one dialect-aware `INSERT ... ON CONFLICT DO
  UPDATE` per table per flush instead, so the query count per flush no longer scales with how many
  distinct clients/domains were active in that window.
- **`raw_events` is indexed client-first.** The hot per-client queries (a client's detail view,
  the sensitive-category anomaly check) filter `WHERE client_ip = ? AND timestamp >= ?`; the index
  now leads with `client_ip` instead of `timestamp` so those queries seek straight to that
  client's rows instead of scanning the timestamp range for every client.
- **Category-based alerting reads a pre-aggregated table, not raw_events per client.**
  `client_category_minute_aggregates` is populated inside `Aggregator.flush()` (one more bucket
  alongside the existing minute/domain/client ones, at the same per-event cost).
  `CategoryUsageMonitorJob` does one `GROUP BY` query across every client instead of looping over
  each active client and re-scanning `raw_events` for it — the query cost no longer scales with
  client count. The tradeoff: "time spent in category X" becomes a proxy (distinct minute-buckets
  with activity), not exact session reconstruction. The precise, session-based per-domain
  breakdown a human reviews for one specific client (`time_spent_service.py`) is unaffected — it's
  a single-client, on-demand query, not a per-check full scan of everyone.
- **Old per-minute client data is rolled up to hourly.** `client_minute_aggregates` rows older
  than `CLIENT_ROLLUP_AFTER_HOURS` (default 48h) get compressed into `client_hourly_aggregates` and
  the source minute rows deleted (`RetentionJob._rollup_client_minutes_to_hourly`) — otherwise a
  "last 30 days" query would mean `GROUP BY` over one row per client per minute for the whole
  window. `client_service.client_bucket_rows` reads both tables via `UNION ALL`, relying on the
  rollup's delete-in-the-same-transaction behavior to guarantee the two tables never cover the
  same instant for the same client, so nothing is double-counted or missed.
- **The ring buffer surfaces when it's falling behind.** If the aggregator can't flush fast enough
  to keep up with incoming events, `deque(maxlen=RING_BUFFER_MAX_EVENTS)` silently drops the
  oldest ones — previously an invisible failure mode. `Aggregator.backlog_ratio`/
  `events_likely_lost` and `/api/health`'s `aggregator_backlog_ratio`/
  `aggregator_events_likely_lost` fields make this observable instead of a silent data loss.
- **`/ws/live` broadcasts are batched.** Every parsed event used to schedule its own asyncio task
  and its own `send_json` per connected viewer; `WebSocketManager` now coalesces events arriving
  within a short window (`BATCH_WINDOW_SECONDS`, default 0.2s, or immediately at
  `MAX_BATCH_SIZE`) into one array per send, so cost no longer scales as (events × viewers) with
  zero batching.

## Sizing for a large client count: a ~30,000-client worked example

The changes above were "measured and hardened," but not against any one stated client count. This
section turns "~30,000 Squid clients" (employees/devices proxied through Squid -- not concurrent
dashboard logins, a different and much smaller kind of load) into concrete config values, sized
against the single-process model above, not around it.

**Traffic math.** Squid clients never talk to the backend/DB directly -- they only produce log
lines `LogTailer` reads from disk. So "30,000 clients" only matters as an input to (a) log lines/sec
the ingest pipeline must absorb, and (b) unique `client_ip` cardinality the client-indexed queries
must handle.

| Step | Reasoning | Value |
|---|---|---|
| Provisioned clients | Given | 30,000 |
| Concurrently active, business hours | Meetings, hybrid work, time away from desk | 70% → 21,000 |
| Logged req/s per active client, average | Squid logs one line per `CONNECT`/request, not per browser sub-resource -- enterprise proxy sizing typically lands around 0.1-0.3 req/s/user during active periods | 0.1 (avg) |
| Logged req/s per active client, peak | Same range, top end, plus synchronized activity (login storms, meeting-end spikes) | 0.3 (peak) |
| **Average target** | 21,000 × 0.1 | **≈2,000 req/s** |
| **Peak target** | 21,000 × 0.3, +30% engineering headroom | **≈8,000 req/s** |

Cross-check: the "1-3M requests/day" figure this codebase's retention batching was already
designed around (see `RetentionJob`'s docstring) implies a much smaller population than 30,000 at
these rates -- that existing assumption was never validated at this scale, so the values below are
sizing *up* from it, not re-confirming it. This is why the load test in step 4 matters as much as
the arithmetic: whether Postgres actually sustains multi-thousand-row bulk-upsert flushes at this
volume on real hardware has to be measured, not just calculated.

**Ring buffer runway.** Buffer capacity ÷ peak events/sec = seconds of runway before
`Aggregator.backlog_ratio`/`events_likely_lost` can go true (see "Ring buffer sizing" above):

| | `RING_BUFFER_MAX_EVENTS` | `AGGREGATION_INTERVAL_SECONDS` | Peak eps | Runway | Headroom |
|---|---|---|---|---|---|
| Demo/small-deployment default | 500,000 | 60s | 8,000 | 62.5s | **<1 flush cycle** |
| **Recommended for ~30k clients** | 1,000,000 | 30s | 8,000 | 125s | **~4 flush cycles** |

At the computed peak, the demo default holds barely more than one flush cycle's worth of events --
a single delayed flush (a transient DB hiccup, a slow query) during a burst risks silent event loss
before it's ever persisted. The recommended values roughly quadruple that runway. Memory cost: at
roughly ~1KB/event, 1,000,000 buffered events costs on the order of ~1GB RAM.

**Recommended settings** (set via `.env`/`docker-compose.override.yml` -- see "Capacity planning
for large deployments" in README.md for how these reach the container):

```
RING_BUFFER_MAX_EVENTS=1000000
AGGREGATION_INTERVAL_SECONDS=30
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

`DATABASE_POOL_SIZE`/`DATABASE_MAX_OVERFLOW` aren't driven by client count at all -- Squid clients
never touch the DB. What drives pool contention is the ~9 independent background jobs in
`main.py` (each opens its own session when it runs, and can overlap) plus larger tables at this
volume meaning individual queries hold their connection longer. A 30-connection ceiling
(10 + 20 overflow) comfortably covers all background jobs overlapping plus ~20 concurrent
API/dashboard requests, well under Postgres's default `max_connections=100`.

**Load-testing this before going live.** `backend/scripts/generate_demo_log.py --clients 30000
--rate 2000` (see its module docstring for running several concurrent copies to reach the full
8,000 req/s peak target) generates realistic client cardinality and rate to exercise this
empirically against `/api/health`'s existing observability fields
(`aggregator_backlog_ratio`, `aggregator_events_likely_lost`, `log_parse_failure_rate`) rather than
trusting the math alone. See README.md's "Capacity planning for large deployments" for the full
verification procedure.

**Disk.** At the average target (~2,000 req/s over a ~10h business day) and the default
`RETENTION_DAYS_RAW_EVENTS=7`, rough volume is ~70-80M `raw_events` rows/day; at an estimated
~300-400 bytes/row (row + index overhead), that's **~150-200GB just for `raw_events` at steady
state with 7-day retention** -- shown as a formula, not false precision, since actual row size
depends on domain-name/URL length distribution in real traffic. The two existing levers if this is
a constraint: `RETENTION_DAYS_RAW_EVENTS` (lower it) and `ARCHIVE_ENABLED`'s existing compression
path (already on by default).

**Measured numbers.** Ran the verification procedure at a scale reduced to fit the dev sandbox
it was run on (12 CPUs, ~2.7GB available RAM shared with other processes — not the ~6GB
backend/~8GB Postgres target hardware above), using `--clients 10000` (not 30000) and rates
scaled proportionally: `RING_BUFFER_MAX_EVENTS=200000`, `AGGREGATION_INTERVAL_SECONDS=30`,
`DATABASE_POOL_SIZE=10`, `DATABASE_MAX_OVERFLOW=20` (pool settings unchanged from the 30k
recommendation — pool sizing isn't RAM-bound). Results, and what they mean for the 30k target:

- **Sustained ~300 events/s** (roughly this test's proportional equivalent of the ~2,000 req/s
  30k-client average target): `aggregator_backlog_ratio` stayed around 0.15, well clear of the
  0.8 warning threshold, `aggregator_events_likely_lost` stayed `false` throughout, backend RSS
  stayed under 160MB. No surprises here — matches the calculated runway.
- **Burst — a real, important finding.** Layering a 4x burst (~1,200 events/s on top of the
  ~300/s sustained load, ~1,500 events/s combined) on this reduced config pushed
  `aggregator_backlog_ratio` to **1.33** and `aggregator_events_likely_lost` to **`true`** —
  despite buffer-capacity math (200,000 ÷ 1,500 ≈ 133s runway vs. a 30s flush interval) predicting
  comfortable headroom. **The actual bottleneck wasn't buffer size — it was Postgres CPU,
  which hit 98% during the burst** (visible via `docker stats`), meaning the aggregator's
  bulk-upsert flush itself became the throughput ceiling, not ring-buffer capacity. This is the
  concrete reason the load test in the verification procedure isn't optional: **buffer-runway
  math alone is necessary but not sufficient — DB write throughput under concurrent flush load is
  a separate, real constraint that has to be measured against the actual provisioned
  CPU/Postgres tuning, not assumed adequate because the buffer math checks out.** On real
  30k-scale hardware (4 dedicated Postgres CPUs + the tuning flags in
  `docker-compose.override.yml.example`, vs. this test's shared, untuned Postgres container),
  this ceiling should sit much higher — but that specific claim is exactly what still needs
  verifying against real target hardware before go-live, not assumed from this smaller run.
- **Recovery was clean.** Once the burst generator stopped, `aggregator_backlog_ratio` drained
  back to 0.07 within about a minute — no deadlock, no stuck state, no manual intervention
  needed.
- **Connection pool held up.** 40 concurrent API requests (mixed authenticated/unauthenticated)
  fired throughout the burst, overlapping with Postgres's CPU saturation — zero connection
  timeouts, zero pool-exhaustion errors in the backend logs, only expected `401`/`200` responses.
  Confirms `DATABASE_POOL_SIZE=10`/`DATABASE_MAX_OVERFLOW=20` (§2) isn't the constraint here even
  under DB-CPU pressure; the constraint was raw Postgres compute, a hardware/tuning question, not
  a pool-sizing one.
- **Memory was never close to a limit** at this scale (peak backend 463MB, peak Postgres 171MB) —
  reinforces that the binding constraint for the burst case was CPU/DB-throughput, not RAM, which
  changes where effort should go when provisioning real hardware: don't over-index on the RAM
  figures above at the expense of the Postgres CPU/tuning ones.

**Still open**: a run at the full `--clients 30000`, `RING_BUFFER_MAX_EVENTS=1000000`,
`AGGREGATION_INTERVAL_SECONDS=30` scale, against hardware actually matching the resource table
above (dedicated Postgres CPUs, the tuning flags applied) — to confirm the burst-vs-Postgres-CPU
finding above doesn't reproduce at the full target scale once Postgres is properly resourced and
tuned, not just scaled down proportionally.

## Not yet built: running more than one backend instance

None of the above changes the deployment model: this app still only runs as **one process**
(`Dockerfile`'s `CMD` has no `--workers`, deliberately). That's because several pieces of state
live only in that process's memory and assume there's exactly one of them running:

- `RingBuffer` and `WebSocketManager` (in-process, per `app.state`)
- `LogTailer` (if two instances both tailed the same log file, every line would be ingested twice)
- `WsTicketStore` (see the ticket-auth section above — already called out as needing a shared
  store like Redis for multi-instance)
- The periodic jobs (`Aggregator`, `RetentionJob`, `CategoryUsageMonitorJob`, `QuotaMonitorJob`,
  `ReportScheduler`) — two instances would double-flush, double-purge, and double-send report
  emails

This is a deliberate scope boundary, not an oversight: making this horizontally scalable would
require splitting the ingestion/background-job singleton out from the request-serving tier (so
only the *serving* tier runs N replicas behind a load balancer), and introducing a shared
pub/sub layer (Redis, or Postgres `LISTEN`/`NOTIFY`) so `/ws/live` broadcasts and the ticket store
work across replicas. That's a real new infrastructure dependency, which this project has
deliberately avoided adding without a concrete reason to — a single, well-tuned instance handles a
large client count and traffic volume (see above), and going multi-instance should be a deliberate
decision made against real capacity numbers from a real deployment, not spec work done in advance
of needing it.

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

**Reading and parsing happen off the event loop.** Every poll's file I/O and parsing runs via
`asyncio.to_thread`, not inline on the event loop — measured at 3.6s to fully freeze the process
(no API response, no WebSocket push, nothing) for a 200k-line backlog before this, which is a real
scenario, not a contrived one: it's exactly what happens when `deploy/rsyslog/`'s disk-queued
lines drain all at once after a branch/central link recovers from an outage (see "Multi-branch
deployment" above). Only dispatching already-parsed events to `on_event` happens back on the
event-loop thread, since `WebSocketManager.broadcast_nowait` schedules asyncio tasks, which isn't
safe from a worker thread. Verified against a live deployment: 340 API requests served (avg
11.8ms) while a 150k-line burst was being ingested, vs. the old implementation's multi-second
total freeze for a comparable backlog.

**Read position survives a restart.** Each tailer persists its position (inode + byte offset) to
`LOG_TAILER_STATE_DIR` after every poll. Previously every fresh `LogTailer` — including one
created by a routine restart, not just a first-ever deploy — opened at the file's current end,
silently skipping whatever Squid wrote while the process was down. A saved position is only
trusted if its inode still matches the current file (otherwise the file was rotated away while
down, and the tailer starts from the beginning of the new file instead, since that may already
hold data written since the rotation); no saved position at all still means "first-ever run,
skip existing history," the original deliberate first-deploy behavior. Verified against a live
deployment: 3068 events written to the log during a 22-second container stop were all correctly
picked up on restart, with no gap in the resulting event timeline.

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

## Going to production: what a demo `docker compose up` doesn't give you

The default `--profile demo` setup runs the whole stack with zero external configuration, which
is deliberately convenient for evaluating the project — but several of the defaults it ships with
are demo-only and must be deliberately changed before a real deployment, not just deployed as-is:

- **`JWT_SECRET` and `ADMIN_PASSWORD` are placeholders in `.env.example`.** Every security
  property in the "Auth" sections above (short-lived access tokens, rotated refresh tokens)
  assumes `JWT_SECRET` is an actual secret; shipping the example value would make every issued
  token forgeable.
- **Squid must log in the native `squid` logformat**, not `common`/`combined` — this is called out
  in the README because it's the single most common go-live failure: the tailer stays "alive" and
  `log_parse_failure_rate` (`/api/health`) goes to `1.0` with no crash, so it silently looks
  connected while showing zero real traffic. Check that field immediately after pointing at a real
  Squid instance, before trusting anything else the dashboard shows.
- **SQLite is fine for evaluating the project, not for a real multi-branch deployment.** It's the
  zero-dependency default (see "SQLite by default" above) specifically so `uvicorn app.main:app`
  works with nothing else running; a real deployment with concurrent writers across branches
  should set `DATABASE_URL` to Postgres, which is what `docker-compose.yml`'s non-demo path
  already wires up.
- **Multi-branch log shipping needs TLS end-to-end, not just `LOG_SOURCES` pointed at a path.**
  `LOG_SOURCES` only tells the backend which *local* files to tail — getting each branch's
  `access.log` onto that machine securely is the separate rsyslog-over-TLS setup in
  `deploy/rsyslog/` (see the README's "Multi-branch deployment" section). Skipping the TLS
  configuration there means branch traffic logs — which include every client IP and every domain
  visited — cross the network in the clear.
- **Capacity settings (`RING_BUFFER_MAX_EVENTS`, `RETENTION_DAYS_RAW_EVENTS`, disk space) need
  sizing against the real deployment's request volume**, not left at defaults tuned for the
  original demo scale — see "Ring buffer sizing is a real capacity tradeoff" above. The failure
  mode when these are undersized (silently dropped ring-buffer events, prematurely purged raw
  events) is observable via `/api/health` but easy to miss if nobody's watching it.
- **This still runs as one process** (see "Not yet built: running more than one backend instance"
  above) — that's a real ceiling on how far a single deployment scales, not something more RAM or
  a bigger database fixes.

None of this is code that needs to change — it's configuration and infrastructure decisions that
have to be made deliberately for a specific deployment, which is why `/api/health` exists: it's
the one place that tells you, after go-live, whether the choices above were actually made
correctly.

## Testing strategy

Backend tests exercise real code paths against a real (in-memory SQLite, `StaticPool`) database
rather than mocking the ORM — including the aggregator's actual `flush()` upsert logic, not just
hand-inserted rows, since that upsert path is where a real bug (freshly-constructed SQLAlchemy
rows have `None` counters until first flush, so `row.total += n` raised on every new bucket) was
caught during manual end-to-end QA and only then back-filled with a regression test
(`tests/test_aggregator.py`). The lesson generalized into a project convention: any service that
writes through the ORM gets at least one test that exercises the real write path, not just a
query built on pre-seeded fixture rows.
