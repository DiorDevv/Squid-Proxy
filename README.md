# Squid Watch — Squid Proxy Log Analytics Dashboard

[![CI](https://github.com/DiorDevv/Squid-Proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/DiorDevv/Squid-Proxy/actions/workflows/ci.yml)
[![CodeQL](https://github.com/DiorDevv/Squid-Proxy/actions/workflows/codeql.yml/badge.svg)](https://github.com/DiorDevv/Squid-Proxy/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/github/license/DiorDevv/Squid-Proxy)](LICENSE)

A real-time log analytics dashboard for Squid Proxy: tails `access.log`, parses and aggregates
traffic, and serves a live "Network Operations Center" style dashboard for a security/compliance
team to see who accessed (or tried to access) what, and what got blocked.

```
Squid Proxy access.log ──tail──> Python backend (FastAPI) ──REST/WS──> React frontend
                                        │
                                        ▼
                                SQLite / PostgreSQL
```

![Squid Watch dashboard](docs/screenshots/dashboard.jpg)

See [ARCHITECTURE.md](ARCHITECTURE.md) for the reasoning behind the major design decisions.

## Table of contents

- [Project layout](#project-layout)
- [Quick start (Docker, recommended)](#quick-start-docker-recommended)
- [Multi-branch deployment (multiple Squid servers)](#multi-branch-deployment-multiple-squid-servers)
- [Quick start (without Docker)](#quick-start-without-docker)
- [Tests & linting](#tests--linting)
- [Configuration reference](#configuration-reference)
- [Capacity planning for large deployments](#capacity-planning-for-large-deployments)
- [Domain categorization](#domain-categorization)
- [Category/quota alerting and scheduled reports](#categoryquota-alerting-and-scheduled-reports)
- [Archiving raw event detail before it's purged](#archiving-raw-event-detail-before-its-purged)
- [Database backups](#database-backups)
- [Operator failure notifications](#operator-failure-notifications)
- [API surface](#api-surface)
- [Deploying without Docker](#deploying-without-docker)
- [Database migrations](#database-migrations)
- [Security notes](#security-notes)
- [Contributing](#contributing)

## Project layout

```
backend/    FastAPI + SQLAlchemy (async) + JWT auth + log tailer/aggregator
frontend/   React + TypeScript + Vite + Tailwind + shadcn/ui
deploy/     Example nginx/systemd for a non-Docker deployment, plus rsyslog configs for
            centralizing logs from multiple branch servers (see "Multi-branch deployment" below)
docker-compose.yml   Backend + frontend + Postgres, wired together
```

## Quick start (Docker, recommended)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# Edit .env: set JWT_SECRET and ADMIN_PASSWORD at minimum.
# JWT_SECRET: python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose --profile demo up --build
```

`--profile demo` additionally starts a synthetic Squid log generator so the dashboard has data to
show without a real Squid deployment (see `backend/scripts/generate_demo_log.py`). Omit
`--profile demo` for a real deployment and instead bind-mount your real Squid log directory (see
below).

Then open **http://localhost:8080** and sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you set
in `.env`.

To point at a **real** Squid installation instead of the demo generator, drop the `demo` profile
and bind-mount the real log directory over the `squid_log_data` volume in `docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      - /var/log/squid:/data/squid-logs:ro
```

### Required Squid configuration — read this before going live

The log parser (`backend/app/services/log_parser.py`) expects Squid's **native `squid`
logformat**, not `common`/`combined` or a custom one. Your `squid.conf` must have:

```
access_log /var/log/squid/access.log squid
```

If `access_log` instead says `common`, `combined`, or names a custom `logformat`, **every line
will silently fail to parse** — the dashboard will look "connected" (the log tailer is alive, it's
reading the file) but show zero traffic, with no crash and no obvious error. This is the single
most common way a real deployment goes wrong, so two things exist specifically to catch it before
it embarrasses you in front of a client:

- **`GET /api/health`** reports `log_lines_seen`, `log_lines_parsed`, and `log_parse_failure_rate`.
  Check this immediately after pointing at a real Squid instance — `log_parse_failure_rate` should
  be at or near `0`, not `1.0`.
- The dashboard itself shows a **red banner on every page** if the failure rate stays high, so this
  isn't something you have to remember to check manually.

If your organization's `access_log` format can't be changed (e.g. other tools already depend on
it), you have two options: add a **second** `access_log` line in `squid.conf` writing the `squid`
format to a separate file for this dashboard to tail, or adapt `parse_line()` in
`log_parser.py` to your actual field layout (its docstring documents the exact 10 fields it
expects, in order).

## Multi-branch deployment (multiple Squid servers)

The backend can ingest several branches/sites at once (`LOG_SOURCES`, see
`backend/.env.example`) into one shared dashboard, each branch tagged and filterable
independently. That config expects every branch's `access.log` to already be a **local file** on
the machine running the backend — the backend itself doesn't reach out to remote servers, so
getting each branch's log there is a separate, infrastructure-level step.

The recommended way to do that is centralizing logs with **rsyslog**, over TLS, in real time:

```
Branch 1 Squid ──access.log──> rsyslog (imfile) ──TLS──┐
Branch 2 Squid ──access.log──> rsyslog (imfile) ──TLS──┼──> Central rsyslog (imtcp) ──> one file per branch ──> LOG_SOURCES
Branch N Squid ──access.log──> rsyslog (imfile) ──TLS──┘
```

Example configs for both ends are in `deploy/rsyslog/`:

- **`deploy/rsyslog/branch.conf`** — installed on each branch server. Tails that branch's
  `access.log` and forwards it to the central server over TLS. If the central server or the link
  between them is down, lines queue to local disk (`queue.type="linkedlist"`, capped at
  `queue.maxdiskspace`) and drain automatically once it's back — no log data is lost to a
  transient outage, it just arrives late.
- **`deploy/rsyslog/central.conf`** — installed on the backend server. Receives each branch's
  stream and writes it back out to its own file, unchanged (no syslog envelope added), so it's
  byte-identical to what Squid wrote — `LogTailer` reads it exactly like a local Squid install.
- **`deploy/rsyslog/check-queue-disk.sh`** — run on each branch server via cron/systemd timer;
  alerts (via `logger`, so it surfaces through whatever monitoring already watches that server)
  if the disk-buffer queue is filling up, which only happens during an extended outage. Catch it
  before the queue hits its cap and starts dropping data.
- **`deploy/rsyslog/squid-branches.logrotate`** — installed on the central server; rotates the
  per-branch files `central.conf` writes (they'd otherwise grow unbounded). Uses `copytruncate`,
  required because rsyslog keeps the destination file open.
- **`deploy/rsyslog/test-single-vm.sh`** — a scratch end-to-end sanity check: runs both the
  branch and central roles on one disposable test VM (over `127.0.0.1`, self-signed test certs),
  sends a marker line through the whole pipeline, and confirms it arrives. Validates the config
  logic (TLS, tag routing, file output) before touching real branch servers; doesn't test
  cross-server firewall/hostnames — see the rollout checklist below for that. Run it on a
  disposable VM, not your main machine (it installs packages and edits `/etc/rsyslog.d/`).

Both `.conf` files use TLS client-cert auth between branch and central — Squid logs contain
client IPs and visited URLs, which is sensitive even on a private network. Generate your own
private CA and per-server certs (e.g. with `openssl req`); this repo doesn't ship real certs or
keys.

### Rollout checklist (per branch)

These are the four things that actually break a real rollout if skipped — check each one
explicitly per branch rather than assuming it "just works" from the config alone:

1. **Firewall**: TCP/6514 open from that branch's IP to the central server. Without this, the TLS
   handshake never even starts — check with `nc -zv <central-host> 6514` from the branch.
2. **Certs**: the branch's TLS client cert's CN/SAN is added to `central.conf`'s `PermittedPeer`
   list (placeholder there — it ships with 4 example hostnames, replace with your real ones), and
   `central.example.internal` in `branch.conf` matches the central server's actual cert name.
3. **File permissions**: the backend process's user (`squid-dashboard` in `deploy/systemd`) can
   read the files rsyslog creates under `/var/log/squid/` on the central server —
   `central.conf`'s `fileCreateMode="0644"` handles this in the common case; if your rsyslog runs
   under a more restrictive umask, add the backend's user to rsyslog's group instead.
4. **`BRANCH_TAG` consistency**: the same string is used in that branch's `branch.conf` (`Tag=`)
   and in the corresponding `LOG_SOURCES` entry's `"branch"` field — a typo here means that
   branch's file never gets created/tailed, with no error, just an empty branch in the dashboard.

**After wiring up each branch, verify it before trusting its data**: check `GET /api/health`'s
`log_sources` array. Each branch's `parse_failure_rate` should be at/near `0` — same check as the
single-branch case above, just per branch instead of global. A branch stuck at `1.0` means that
branch's Squid is logging in the wrong format (see "Required Squid configuration" above), not a
transport problem.

This setup is deliberately **only about getting logs to the backend reliably** — the backend
itself still runs as a single instance by design (see `ARCHITECTURE.md`'s "Not yet built: running
more than one backend instance"). A branch or network outage delays that branch's data; the
backend process going down loses no data (Squid/rsyslog keep buffering) but does pause live
monitoring until it restarts, which `deploy/systemd`'s `Restart=on-failure` already handles
automatically. Building the backend itself into a multi-instance/HA setup is a bigger, separate
undertaking that isn't warranted here — see that same `ARCHITECTURE.md` section for why.

### Restricting a user to one branch

By default every account (`admin` or `viewer`) can see every configured branch — this is what
"branch" means to a user's *role*, and it's unrelated. To give someone (e.g. a branch-office
manager) access to only their own branch's traffic, set their **Branch** to that branch at
**Settings → User management**, in the same row as their role, when creating the account or at
any time afterward (`PATCH /api/users/{id}/branch`). Once set:

- Every data-read endpoint (events, clients, domains, timeseries, summary, insights, exports)
  transparently returns only that branch's data — a request that doesn't specify `branch` is
  filled in with the user's own branch automatically; a request that explicitly asks for a
  *different* branch gets a 403, not silently-wrong data.
- The dashboard's branch selector hides itself for a scoped user (there's nothing to switch
  between), the same way it already does for a genuinely single-branch deployment.
- Admin-only settings (alert thresholds, domain categories, export cleanup policy, scheduled
  reports) are **not** branch-restricted — this only ever narrows *data visibility*, never what an
  admin account is allowed to configure.

Leaving Branch as **All branches** (the default) keeps today's behavior exactly — this is
additive, no existing account's access changes.

## Quick start (without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env: LOG_FILE_PATH (point at a real or demo access.log), JWT_SECRET, ADMIN_PASSWORD.

uvicorn app.main:app --reload
```

The backend auto-creates its SQLite database and bootstraps the first admin user (from
`ADMIN_EMAIL`/`ADMIN_PASSWORD`) on first run. To add more users later:

```bash
python scripts/create_admin.py --email viewer@example.com --password '...' --role viewer
```

To exercise the dashboard without a real Squid proxy, run the synthetic log generator in another
terminal, pointed at the same `LOG_FILE_PATH`:

```bash
python scripts/generate_demo_log.py --output /path/to/access.log --rate 30
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # defaults already point at http://localhost:8000
npm run dev
```

Open **http://localhost:5173**.

## Tests & linting

```bash
# Backend
cd backend && source .venv/bin/activate
pytest              # unit + integration tests
ruff check .         # lint
mypy app             # static type checking

# Frontend
cd frontend
npm run build         # strict TypeScript build
npm run lint           # ESLint
npm run test            # Vitest unit/component tests
```

### End-to-end tests

`frontend/e2e/` has a Playwright smoke suite (login, dashboard, Blocked, Clients) that drives the real, wired-together app in a real browser, unlike the unit tests above. It needs the **backend already running** with a bootstrapped admin user (Playwright only starts the frontend dev server):

```bash
# In one terminal: start the backend as in "Quick start" above.
# In another:
cd frontend
npm run test:e2e
```

Defaults assume the backend at `http://localhost:8000` and the documented dev admin credentials (`admin@example.com` / `admin12345`); override with `E2E_API_BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` if yours differ.

## Configuration reference

All backend settings are environment variables — see `backend/.env.example` for the full list
(log file path, database URL, JWT secret, retention windows, CORS origins, rate limits). Frontend
build-time settings are in `frontend/.env.example` (API/WebSocket base URLs).

Key ones to know:

| Variable | Purpose |
|---|---|
| `LOG_FILE_PATH` | Path to the Squid `access.log` to tail — must be written in the `squid` logformat, see above |
| `DATABASE_URL` | `sqlite+aiosqlite:///...` (default) or `postgresql+asyncpg://...` |
| `JWT_SECRET` | Signs access tokens — must be set to a real secret in any non-dev environment |
| `RETENTION_DAYS_RAW_EVENTS` / `RETENTION_DAYS_AGGREGATES` | How long raw vs. aggregated data is kept |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First-boot admin bootstrap (only used if the `users` table is empty) |
| `RING_BUFFER_MAX_EVENTS` / `AGGREGATION_INTERVAL_SECONDS` | In-memory event buffer size and flush interval — see "Capacity planning" below |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | Postgres connection pool sizing (ignored for SQLite) — see "Capacity planning" below |
| `OPS_ALERT_WEBHOOK_URL` | Notified when something breaks operationally (tailer down, backup/retention/archiving failed) — see "Operator failure notifications" below |

## Capacity planning for large deployments

The defaults above are sized for evaluating the project or a small deployment, not validated
against a specific large client count. If you're deploying against a large population of proxied
clients (tens of thousands of employees/devices through Squid — not concurrent dashboard logins,
a much smaller and different kind of load), size these deliberately instead of leaving them at
their demo-scale defaults. See "Sizing for a large client count" in `ARCHITECTURE.md` for the full
reasoning (traffic-math derivation, ring-buffer runway table, why pool size isn't actually driven
by client count) — summarized here:

**For a ~30,000-client deployment**, set in `.env` (docker-compose picks these up automatically —
see `.env.example`):
```
RING_BUFFER_MAX_EVENTS=1000000
AGGREGATION_INTERVAL_SECONDS=30
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
BACKEND_MEMORY_LIMIT=6g
BACKEND_CPU_LIMIT=2
POSTGRES_MEMORY_LIMIT=8g
POSTGRES_CPU_LIMIT=4
```
and copy the Postgres write-heavy-workload tuning flags (`shared_buffers`, `effective_cache_size`,
`max_wal_size`) from `docker-compose.override.yml.example` — the only part of large-deployment
sizing that still needs an override file rather than a plain `.env` variable.

**Required host sizing at this scale** (see `ARCHITECTURE.md` for the derivation):

| Resource | Approximate requirement | Why |
|---|---|---|
| Backend RAM | ~6GB | ~1GB for a 1M-event ring buffer + app baseline + burst-parsing margin |
| Backend CPU | ~2 cores | Off-event-loop log parsing (`asyncio.to_thread`) + API serving |
| Postgres RAM | ~8GB | Write-heavy bulk-upsert workload (every `AGGREGATION_INTERVAL_SECONDS`) |
| Postgres CPU | ~4 cores | Same, plus hourly batched retention purge |
| Disk (`raw_events`) | ~150-200GB | 7-day default retention at the computed request volume — see the formula in `ARCHITECTURE.md`; lower `RETENTION_DAYS_RAW_EVENTS` or rely on `ARCHIVE_ENABLED`'s compression path if disk is constrained |

**Verifying this actually holds up, before go-live:**

1. Deploy with the settings above.
2. Warm up: `backend/scripts/generate_demo_log.py --rate 2000 --clients 30000` for ~10-15 minutes
   (run several concurrent copies against the same `--output` path to reach higher rates — a
   single process has a real CPU-bound ceiling, see the script's docstring).
3. Burst: let the script's built-in burst logic fire, or run a second instance at `--rate 8000`
   for a few minutes to simulate a peak-minute concentration.
4. Poll `GET /api/health` throughout. **Hard pass/fail gate: `aggregator_events_likely_lost` must
   stay `false` for the entire run, including the burst.** Also watch `aggregator_backlog_ratio`
   (should stay well under `0.8`), `log_parse_failure_rate` (should track the injected
   `--malformed-rate`), and `log_tailer_alive` (must stay `true`).
5. While under load, loop-curl a couple of real dashboard endpoints (e.g. `/api/summary`,
   `/api/clients`) and check backend logs for connection-pool exhaustion errors — confirms the
   pool settings hold under human-driven traffic layered on top of the ingest burst.
6. After stopping the load, confirm `aggregator_backlog_ratio` drains back toward `0` within a
   couple of `AGGREGATION_INTERVAL_SECONDS`, and that `docker stats`/disk growth during the run
   stayed within the resource table above.

## Domain categorization

Every domain seen in traffic gets a category (`social_media`, `gambling`, `adult_content`, ...)
used throughout the dashboard and by the alerting below. Three sources, in order of precedence:

1. **Admin override** (`GET`/`PUT /api/domain-categories`) — always wins, since a human said so.
2. **UT1 bulk blacklist** *(optional, off by default)* — millions of domains across gambling,
   adult, gaming, social media, music streaming, video streaming, shopping, and news, from
   [UT1](https://dsi.ut-capitole.fr/blacklists/) (Universite Toulouse Capitole), a free list built
   specifically for this kind of filtering and updated roughly daily upstream. Enable with
   `UT1_ENABLED=true`; it then downloads at startup and refreshes every `UT1_REFRESH_INTERVAL_SECONDS`
   (default weekly) — see `backend/.env.example`. Left off by default because it's a third-party
   server reached over the internet at runtime, which shouldn't happen silently for a
   compliance/security tool. Memory-lean by design (a sorted array of domain hashes, not the
   domains themselves): ~40MB resident once loaded, briefly ~500MB during a refresh (a background
   thread, not the request-handling event loop) — disk cache is ~120MB under `UT1_DATA_DIR`.
3. **Built-in curated list** (`backend/app/services/category_inference.py`) — a small
   (~90-domain) hand-picked list plus a few TLD/keyword heuristics (e.g. `.bet`/`.casino` →
   gambling). Always active, zero setup; covers the common cases UT1's bulk categories don't
   encode the same nuance for (e.g. `aws.amazon.com` is `work_tools`, not `shopping`, even though
   the bare domain is).

Anything none of the three catches is `uncategorized` — the same as if an admin simply hasn't
gotten to it yet, not an error.

## Category/quota alerting and scheduled reports

Beyond the built-in traffic-spike/new-blocked-domain/client-blocked-ratio checks
(`INSIGHTS_PROVIDER=statistical`), three more anomaly checks run automatically once configured:

- **Sensitive category visits** — flags a client's first-ever visit to a domain in an
  admin-chosen category (e.g. gambling, gaming). Checked on every aggregator flush.
- **Excessive non-work category time** — flags a client whose combined time in non-work
  categories exceeds an admin-chosen daily threshold. Checked hourly (`CATEGORY_MONITOR_INTERVAL_SECONDS`).
- **Client data quota** — flags a client exceeding an admin-chosen daily data quota. Checked
  hourly (`QUOTA_MONITOR_INTERVAL_SECONDS`).

All three are **off by default** (nothing configured) and tuned by an admin at
**Settings → Alert settings** (`GET`/`PUT /api/alert-settings`) — not environment variables, since
these are business policy an admin should be able to change without a redeploy. Anomalies raised
by any of them flow through the same `AnomalyEvent`/webhook pipeline as the built-in checks (see
`ALERT_WEBHOOK_URL` below). A fourth check, **undownloaded exports**, is configured separately at
**Settings → Export cleanup settings** — see below.

`ALERT_WEBHOOK_URL` (optional; off by default) receives an HTTP POST for each anomaly at or above
`ALERT_MIN_SEVERITY`. The payload is **Slack-compatible as-is** — point it at a Slack incoming
webhook URL and it renders correctly (a `"text"` field is included alongside the structured
`title`/`description`/`severity`/`client_ip`/`domain`/`branch`/`generated_at` fields, for any
non-Slack consumer). See `OPS_ALERT_WEBHOOK_URL` (below, "Operator failure notifications") for the
separate infra-failure channel.

`TELEGRAM_BOT_TOKEN`/`TELEGRAM_SUPER_ADMIN_CHAT_ID` (optional; off by default, see
`backend/.env.example`) add Telegram as a second delivery channel for the same anomalies, gated by
the same `ALERT_MIN_SEVERITY`. One bot serves every chat: `TELEGRAM_SUPER_ADMIN_CHAT_ID` always
gets every branch's alerts; each branch's own chat is set independently by that branch's admin at
**Settings → Alert settings** (with a "Send test message" button to verify the chat ID before
saving it) and only receives that branch's alerts.

Scheduled email reports (a periodic summary + CSV attachment) are configured via
`REPORT_SCHEDULE` (`disabled` | `daily` | `weekly`), `REPORT_RECIPIENTS`, and `SMTP_*` — see
`backend/.env.example`. These *are* environment variables (SMTP credentials are infrastructure
secrets). **Settings → Scheduled reports** shows status and has a "Send report now" button for
testing without waiting for the schedule.

## Archiving raw event detail before it's purged

Full per-request detail (`raw_events` — every URL, client, timestamp) is only kept for
`RETENTION_DAYS_RAW_EVENTS` (default 30 days) before `RetentionJob` permanently deletes it; only
the smaller per-minute/per-hour aggregates survive long-term (`RETENTION_DAYS_AGGREGATES`, default
~400 days). That's the right tradeoff for the live database, but if your organization needs to
keep the full detail longer (e.g. a compliance requirement), it needs to be archived externally
before it ages out.

**This now happens automatically, out of the box.** `ARCHIVE_ENABLED` defaults to `true`: an
in-process job (`ArchiveScheduler`, started the same way `RetentionJob`/`Aggregator`/etc. are)
periodically writes one gzip-compressed CSV per configured branch
(`squid-events-<branch>-<since>_<until>.csv.gz`) to `ARCHIVE_OUTPUT_DIR` (default `./archives`;
the Docker path bind-mounts this to `./archives` next to `docker-compose.yml` on the host,
rather than a Docker-managed named volume, specifically so the files are directly
browsable/downloadable -- `ls`, SFTP, `rsync` to off-site storage -- without going through
`docker compose exec`/`cp` first), and prunes archive files older than `ARCHIVE_KEEP_DAYS`
(default 365) from there. No setup required for the common case.

**Encrypt archives at rest.** These files carry the same client-IP/domain-visited detail as the
live database. Set `ARCHIVE_ENCRYPTION_KEY` (generate one with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and
every archive from then on is written as `....csv.gz.enc` instead — encrypted before it ever
touches disk. Decrypt with:

```bash
cd backend
.venv/bin/python scripts/decrypt_archive.py --key-file /path/to/key.txt archives/squid-events-*.csv.gz.enc
```

Keep a copy of that key somewhere other than this server (a password manager, a separate secrets
store) — it's the only thing standing between this server's disk being lost/stolen and every past
archive being unreadable either way. Unset (the default) writes plain gzip, matching every archive
a deployment predating this setting already wrote.

**This alone is not a disaster-recovery plan.** `ARCHIVE_OUTPUT_DIR` and the Postgres backups
under [Database backups](#database-backups) below both default to local Docker volumes — on the
*same* disk as the live database. Encrypting archives protects them from someone reading the
disk; it does nothing if the disk itself is lost (hardware failure, a deleted VM, ransomware).
Copying archives and backups to storage on a different machine — another server, an S3-compatible
bucket, anything not on this host — is a deliberate step you still need to add yourself; nothing
here does it for you.

If you'd rather manage this fully yourself instead — a different external destination, your own
cron/systemd timer, tighter control over exactly when it runs — set `ARCHIVE_ENABLED=false` and
use the same logic via the standalone script:

```bash
cd backend
.venv/bin/python scripts/archive_weekly_export.py --output-dir /path/to/archive --keep-days 365
```

```
0 3 * * 0  cd /path/to/backend && .venv/bin/python scripts/archive_weekly_export.py --output-dir /var/backups/squid-watch
```

Either way, each run streams in batches rather than holding rows in memory, so there's no row
limit — a week of raw events at real traffic volumes is routinely millions of rows.

`GET /api/export` streams the same way and is equally uncapped — pick `range=7d` there for an
ad-hoc download of the full week straight from the browser, no server access needed. The **Export**
button on **Settings** covers the same ad-hoc use case but goes through `POST /api/export/jobs`
instead (a background job, polled via `GET /api/export/jobs/{id}` and downloaded once `DONE`) rather
than calling `GET /api/export` directly — the UI trades a held-open connection for a progress-visible
job it can also share a time-limited download link for (`POST /api/export/jobs/{id}/share`), without
giving up the row limit either way. The difference from archiving below is what each is *for*: an
ad-hoc pull (either endpoint) is fine for an occasional manual download, but its output isn't
gzip-compressed and isn't pruned automatically the way an archive is (background-job results do get
cleaned up per **Settings → Export cleanup settings**, but that's retention housekeeping, not
long-term storage). Archiving is the one built for unattended, ongoing retention, since it also
gzip-compresses (roughly 15x smaller) and prunes its own old files.

**If archiving ever stops running** (disabled, disk full, etc.), you're not left finding out the
hard way once the data is already gone. Every successful run records how far it archived
(`archive_runs` table); before each purge, `RetentionJob` checks whether the branch it's about to
delete raw data for was actually covered, and if not, still purges (retention has to stay bounded
regardless) but surfaces a warning both on the dashboard (a banner, same mechanism as the
Squid-logformat one above) and by email to `REPORT_RECIPIENTS`, if configured. Seeing that warning
means archiving needs attention *before* more data ages out unarchived — not after.

**Result files from `GET /api/export/jobs` (the background export used by the Settings page for
large ranges) are cleaned up automatically too**, on an admin-tunable policy at
**Settings → Export cleanup settings** (`GET`/`PUT /api/export-settings`) rather than an
environment variable, for the same reason alert thresholds are: it's a policy an admin should be
able to change without a redeploy. Two mutually exclusive modes — only one applies at a time:

- **Time-based** *(default, 120h / 5 days)* — a finished export file is deleted once it's older
  than the configured retention period, downloaded or not. Long enough to survive a weekend (a
  plain 48h window silently loses a Friday-afternoon export by Monday morning); lower it, or
  switch to After download below, if disk space is the binding constraint instead.
- **After download** — a finished export file is deleted the moment it's successfully downloaded,
  regardless of age. Useful when disk space is tight. A file that's *never* downloaded in this
  mode is never auto-deleted by age — nothing schedules its deletion — so pair it with the warning
  below.

Independently of which mode is active, **`warn_undownloaded_after_hours`** *(default 24h)* raises
a dashboard anomaly once a finished export has sat undownloaded that long — e.g. an export kicked
off mid-week and then forgotten. On by default (unlike the alerting checks above, which are
business policy) since this specifically guards against the time-based mode above silently
deleting a file nobody ever got to download; set it back to unset/null to turn it off. Same
`AnomalyEvent`/webhook pipeline as the category/quota alerting checks above.

## Database backups

**Archiving above is not a database backup.** It covers exactly one table (`raw_events`), and only
what's about to be purged by `RETENTION_DAYS_RAW_EVENTS`. Users, alert settings, aggregates, the
audit log, export-job history — everything else — has no equivalent unless you set this up. If
`postgres_data` (or your SQLite file) is lost or corrupted with no backup, all of that is gone
permanently.

**Docker**: a dedicated `db-backup` service runs automatically as part of `docker compose up`
(`docker-compose.yml`) — no separate setup needed. It's built from `postgres:16-alpine` specifically
(not the Python backend image), so `pg_dump` is guaranteed to match the server's exact version. Dumps
land in the `db_backup_data` volume as `squid-dashboard-backup-<timestamp>.dump` (Postgres custom
format — compressed, supports selective restore), once a day by default
(`BACKUP_INTERVAL_SECONDS`), pruned after `BACKUP_KEEP_DAYS` (default 30).

**Without Docker**: install `postgresql-client` (matching your server's major version) or `sqlite3`,
whichever `DATABASE_URL` calls for, then run `backend/scripts/backup_database.py` on a schedule —
`deploy/systemd/squid-dashboard-backup.{service,timer}` does this daily, install the same way as
the backend unit:

```bash
sudo cp deploy/systemd/squid-dashboard-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now squid-dashboard-backup.timer
```

Or run it manually / via your own cron:

```bash
cd backend
.venv/bin/python scripts/backup_database.py --output-dir /var/backups/squid-watch --keep-days 30
```

**Restoring** — a backup nobody's tested restoring from isn't a real backup:

```bash
# Postgres (custom format -- pg_restore, not psql):
pg_restore --clean --if-exists --dbname=postgresql://squid:PASSWORD@localhost:5432/squid_dashboard \
  squid-dashboard-backup-20260101T040000Z.dump

# SQLite -- the backup file is already a complete, standalone database:
cp squid-dashboard-backup-20260101T040000Z.db squid_dashboard.db
```

**Verifying restores automatically**: `backend/scripts/verify_backup_restore.py` (non-Docker) /
`verify_backup_restore_docker.sh` (Docker) automate exactly this — restore the newest backup into
a throwaway database, run a minimal sanity query, then drop it, never touching the real database.
Not run on the same schedule as the backup itself (restoring a full dump isn't cheap); weekly is
enough to catch a broken backup mechanism well before the default 30-day retention window would
otherwise let a run of bad backups go unnoticed.

```bash
# Docker:
docker compose exec db-backup sh /verify_backup_restore_docker.sh

# Without Docker -- install the same way as the backup timer above:
sudo cp deploy/systemd/squid-dashboard-backup-verify.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now squid-dashboard-backup-verify.timer
```

A failed verification (or a failed backup itself, or a failed retention/archive run, or the log
tailer dying) posts to `OPS_ALERT_WEBHOOK_URL` if configured — see "Operator failure
notifications" below.

## Operator failure notifications

Distinct from the traffic-anomaly `ALERT_WEBHOOK_URL` above: `OPS_ALERT_WEBHOOK_URL` (falls back to
`ALERT_WEBHOOK_URL` if unset, so a single-webhook operator needs zero new config) is posted to
whenever something operational breaks — the log tailer dies, a background job (retention,
archiving, category/quota/UT1 checks) errors out, a backup or backup-restore-verification fails.
Every one of these already logged the failure and retried on its own schedule; this is what
actually reaches a human instead of only whoever happens to be reading `docker logs`/`journalctl`
at that moment. Off by default, same as `ALERT_WEBHOOK_URL`.

## API surface

All endpoints are under `/api`, JWT-protected except `/api/health`. See
`backend/app/api/routes/` for the full set: `auth`, `summary`, `timeseries`, `domains` (top
visited/blocked, by-category, per-domain detail), `clients` (+ per-client activity, time-spent by
domain/category), `alert-settings`, `export-settings`, `reports` (status, send-now), `events`
(recent, ring-buffer-backed), `export` (admin-only CSV/JSON), plus the `/ws/live` WebSocket for real-time
push. Interactive docs are available at `/docs` when the backend is running (FastAPI's built-in
Swagger UI).

**`GET /api/audit-log`** (admin-only) is the who-did-what trail for admin actions: user
management (create/role-change/password-reset/delete), the full export lifecycle
(create/download/share/cancel/share-revoke), and every settings change that affects what gets
flagged or exported (alert settings, domain categories, export cleanup policy, "send report now").
Not a data-retention log — entries survive the account or resource they describe (see
`app/models/audit_log.py`).

**`GET /metrics`** (unauthenticated, same trust boundary as `/api/health`) exposes the same
operational numbers `/api/health` reports — log lines seen/parsed per branch, parse failure rate,
tailer liveness, aggregator backlog ratio — in Prometheus text format, for wiring into
Grafana/Alertmanager instead of scraping and reshaping `/api/health`'s JSON.

## Deploying without Docker

See `deploy/systemd/squid-dashboard-backend.service` (runs the backend as a systemd service, and
runs `alembic upgrade head` via `ExecStartPre=` before every start so schema changes are applied
automatically -- see "Database migrations" below) and `deploy/nginx/squid-dashboard.conf` (serves
the built frontend, reverse-proxies `/api` and `/ws` to the backend, terminates SSL). For multiple
branch servers, see `deploy/rsyslog/` and the "Multi-branch deployment" section above. Build the
frontend for this path with:

```bash
cd frontend
VITE_API_BASE_URL=https://dashboard.example.com VITE_WS_URL=wss://dashboard.example.com npm run build
```

(or leave both unset/empty to use the same origin the page is served from, matching the nginx
config's same-origin proxy setup).

## Database migrations

Schema changes go through Alembic (`backend/app/db/migrations/`), not just the app's own
`init_db()` at startup -- that only ever creates tables that don't exist yet, it never alters an
existing one, so it can't apply a later column/enum change to a table that's already there.

Both deploy paths run `alembic upgrade head` automatically, before the app starts:

- **Docker**: the image's entrypoint (`backend/docker-entrypoint.sh`) runs it whenever the
  container's command is `uvicorn` (i.e. the `backend` service; `demo-log-generator` reuses the
  same image but isn't affected, since its own command doesn't need a database at all).
- **systemd**: `deploy/systemd/squid-dashboard-backend.service`'s `ExecStartPre=` runs it before
  `ExecStart=` on every start/restart.

For local dev (`uvicorn app.main:app --reload` directly, per "Quick start" above), you don't need
to do anything extra: a fresh, empty SQLite database is created entirely by `init_db()`'s
`create_all()`, which produces the full current schema in one shot with no migration history
needed.

**Upgrading an existing database that predates this** (i.e. one that was only ever bootstrapped by
`create_all()`, with no `alembic_version` table yet) needs a one-time manual step first:

```bash
cd backend && alembic stamp head
```

Without this, `alembic upgrade head` has no record of what's already applied, so it tries to
replay every migration from the very first one against tables that already exist, and fails on the
first one it hits with "table already exists". `alembic stamp head` marks the database as already
being at the latest revision without running any of that DDL again -- correct here specifically
because a `create_all()`-only database already has the *current* code's full schema, just without
Alembic's bookkeeping table recording it.

## Security notes

- Access tokens are short-lived (default 20 min) and kept in memory on the frontend only, never
  `localStorage`. Refresh tokens are `httpOnly` cookies, rotated on every use.
- The login endpoint is rate-limited (`LOGIN_RATE_LIMIT`, default 5/minute per IP).
- `viewer` role has full read access; only `admin` can export data or reach `/settings`. Either
  role can additionally be scoped to one branch — see "Restricting a user to one branch" above.
- Branch-scoping covers REST data-read endpoints, `GET /api/branches`, and the `/ws/live`
  live-events WebSocket — a scoped user's connection is filtered to their own branch's events
  server-side, not just hidden client-side.
- Never commit a real `.env` — both `.gitignore` files exclude it; only `.env.example` files are
  tracked.
- **The Docker Compose path (`docker-compose.yml`) serves the frontend over plain HTTP, with no
  TLS termination anywhere in that stack.** That's fine for `http://localhost:8080` (browsers
  treat `localhost` as a secure context, so the `httpOnly` refresh cookie's `Secure` flag — set
  whenever `ENVIRONMENT=production`, the Compose default — still works) or for reaching a remote
  host through an SSH tunnel (`ssh -L 8080:localhost:8080 user@host`, then browse to
  `http://localhost:8080` as usual). **Do not** publish `FRONTEND_PORT` on a remote host's public
  IP/firewall and browse to it directly — the login password and bearer/refresh tokens would
  cross the network in cleartext, and you'd be tempted to set `ENVIRONMENT=development` to stop
  the browser rejecting the now-not-secure-context cookie, which removes the `Secure` flag
  entirely. For real multi-user production access beyond a single admin's SSH tunnel, terminate
  TLS in front of it — see `deploy/nginx/squid-dashboard.conf` for a Let's Encrypt-based example
  (adapt it as a reverse proxy in front of the Compose `frontend` service, or use the bare-metal
  "Deploying without Docker" path directly).

## Contributing

Bug reports, feature requests, and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a dev environment, run the test suite, and
what a good pull request looks like here.
