# Squid Watch — Squid Proxy Log Analytics Dashboard

A real-time log analytics dashboard for Squid Proxy: tails `access.log`, parses and aggregates
traffic, and serves a live "Network Operations Center" style dashboard for a security/compliance
team to see who accessed (or tried to access) what, and what got blocked.

```
Squid Proxy access.log ──tail──> Python backend (FastAPI) ──REST/WS──> React frontend
                                        │
                                        ▼
                                SQLite / PostgreSQL
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the reasoning behind the major design decisions.

## Project layout

```
backend/    FastAPI + SQLAlchemy (async) + JWT auth + log tailer/aggregator
frontend/   React + TypeScript + Vite + Tailwind + shadcn/ui
deploy/     Example nginx (bare-metal) and systemd unit for a non-Docker deployment
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

# Frontend
cd frontend
npm run build         # strict TypeScript build
npm run lint           # ESLint
```

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
`ALERT_WEBHOOK_URL` below).

Scheduled email reports (a periodic summary + CSV attachment) are configured via
`REPORT_SCHEDULE` (`disabled` | `daily` | `weekly`), `REPORT_RECIPIENTS`, and `SMTP_*` — see
`backend/.env.example`. These *are* environment variables (SMTP credentials are infrastructure
secrets). **Settings → Scheduled reports** shows status and has a "Send report now" button for
testing without waiting for the schedule.

## API surface

All endpoints are under `/api`, JWT-protected except `/api/health`. See
`backend/app/api/routes/` for the full set: `auth`, `summary`, `timeseries`, `domains` (top
visited/blocked, by-category, per-domain detail), `clients` (+ per-client activity, time-spent by
domain/category), `alert-settings`, `reports` (status, send-now), `events` (recent,
ring-buffer-backed), `export` (admin-only CSV/JSON), plus the `/ws/live` WebSocket for real-time
push. Interactive docs are available at `/docs` when the backend is running (FastAPI's built-in
Swagger UI).

## Deploying without Docker

See `deploy/systemd/squid-dashboard-backend.service` (runs the backend as a systemd service) and
`deploy/nginx/squid-dashboard.conf` (serves the built frontend, reverse-proxies `/api` and `/ws`
to the backend, terminates SSL). Build the frontend for this path with:

```bash
cd frontend
VITE_API_BASE_URL=https://dashboard.example.com VITE_WS_URL=wss://dashboard.example.com npm run build
```

(or leave both unset/empty to use the same origin the page is served from, matching the nginx
config's same-origin proxy setup).

## Security notes

- Access tokens are short-lived (default 20 min) and kept in memory on the frontend only, never
  `localStorage`. Refresh tokens are `httpOnly` cookies, rotated on every use.
- The login endpoint is rate-limited (`LOGIN_RATE_LIMIT`, default 5/minute per IP).
- `viewer` role has full read access; only `admin` can export data or reach `/settings`.
- Never commit a real `.env` — both `.gitignore` files exclude it; only `.env.example` files are
  tracked.
