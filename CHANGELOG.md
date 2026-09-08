# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed

- **Background jobs no longer wake in lockstep.** The ~9 `IntervalJob`
  schedulers are all started together at boot and several share an interval,
  so they hit the database as one synchronized burst every cycle. Each now
  adds a random 0–60s to its *first* wait only (`max_startup_jitter_seconds`,
  additive so it never fires early); once offset they stay offset.
- **Shutdown is bounded.** The lifespan teardown stopped ~13 jobs one
  `await` at a time; each `.stop()` is individually capped (5–10s) but
  serially that could exceed a container's stop-grace. Tailers still stop
  before the aggregator's final flush (checkpoint ordering), but everything
  after that is now stopped concurrently.
- **`EXPORT_JOBS_MAX_TOTAL_MB`** (default 2048) caps the total on-disk size
  of `EXPORT_JOBS_DIR`; a new export is refused with `507` once it's at the
  limit. `EXPORT_JOB_MAX_CONCURRENT` only bounded how many run at once, not
  how much finished output accumulates.
- **`METRICS_ALLOWED_IPS`** (default empty = unchanged) optionally restricts
  `/metrics` to a set of client IPs/CIDRs. `/api/health` stays open (the
  frontend banner polls it).
- **CI now enforces a coverage floor** (`--cov`, `fail_under = 85`; current
  ~91%) and Dependabot no longer opens automatic major-version PRs (grouped
  minor/patch only; security advisories still come through regardless).
- **`BCRYPT_ROUNDS`** (default 12) is configurable so the test suite can drop
  it to 4 — cut the backend suite from ~200s to ~65s. Never lower it in a
  real deployment.
- **Analytics → Blocks: the "ACL denied" tile is now "Forbidden (403)".** It
  counts every `403`, and a `403` can equally be the destination server's own
  refusal (a geo-block, a WAF, an expired session), not just a Squid ACL — the
  aggregates can't tell the two apart. Relabelled, "Other blocked" → "Other
  denied", and a note spells out that only `407` is always the proxy. No data
  or API change: `blocked` still counts proxy denials plus any `403`/`407`.
- **Branch risk score carries a disclaimer.** It's an uncalibrated heuristic
  for ordering branches by where to look first, not a measured or validated
  risk value — the panel now says so (per `docs/PRODUCT.md`).
- **"Time spent" is labelled an estimate.** The per-domain / per-category
  figures on a client's detail page are derived from gaps between requests
  (`SESSION_GAP_MINUTES`), not measured session time; the panel now says so.
- Documented exactly what `blocked` counts, and the proxy-vs-upstream
  ambiguity it deliberately doesn't resolve, in `ARCHITECTURE.md`.
- Corrected a stale "`RETENTION_DAYS_RAW_EVENTS` default 7" in `ARCHITECTURE.md`
  / `README.md` — the shipped default is 30. The ~30k-client capacity example
  now shows ~25–30 GB/day of raw detail and recommends ~7 days *at that scale*.
- **Alembic is now the single schema authority.** `init_db()` skips
  `Base.metadata.create_all()` entirely once a database has an
  `alembic_version` table, so a real deployment can no longer have a second,
  silent "create anything missing" pass papering over a model added without a
  migration. CI now runs `alembic upgrade head && alembic check` on every
  push to catch that drift. `create_all` still runs on the two genuinely
  Alembic-free paths (a bare `uvicorn app.main:app` dev DB, and the tests).
- **One canonical model list.** `env.py` (Alembic) and `init_db()` each kept
  their own hand-maintained, *different*, incomplete list of model modules to
  import — `env.py` was missing 5 tables, `init_db()` was missing 5 others.
  Both now import `app/models/__init__.py`, which registers every model. Side
  effect: a fresh bare-`uvicorn` dev database now gets all 24 tables, not the
  ~19 the old `init_db()` list happened to name.
- **JWT: `python-jose` → PyJWT.** `python-jose` has been unmaintained since
  2021 and carries open algorithm-confusion / DoS advisories; PyJWT is the
  actively-maintained reference implementation. Behaviour-equivalent (HS256).
- **JWT secret rotation without a mass logout.** `JWT_SECRET_PREVIOUS`, if
  set, is accepted for *verification* alongside `JWT_SECRET` — set it to the
  old value for one access-token lifetime after rotating, then clear it.
  Tokens now also carry a `kid` header (a non-reversible fingerprint of the
  signing secret) used as a decode hint.
- **Per-account login throttle.** On top of the existing per-IP
  `LOGIN_RATE_LIMIT`: after `LOGIN_ACCOUNT_FAILURE_THRESHOLD` (default 10)
  failed logins for one email within `LOGIN_ACCOUNT_FAILURE_WINDOW_SECONDS`,
  that email is limited to one attempt per
  `LOGIN_ACCOUNT_THROTTLED_INTERVAL_SECONDS` (default 60) regardless of
  source IP — closing the gap where a distributed attacker brute-forces one
  account across many IPs. Not a lockout: a correct password still works and
  clears it, and a blocked attempt is indistinguishable (same 401, same
  bcrypt time) from an ordinary wrong password.
- **Production refuses a SQLite `DATABASE_URL`** unless `ALLOW_SQLITE_IN_PRODUCTION=true` is set
  explicitly. SQLite is a single-writer file; under this app's ~9 background jobs plus the
  aggregator all writing, a real deployment on it hits "database is locked". Development is
  unaffected (SQLite stays the zero-config default there).
- **Auditor role.** A third role between `viewer` and `admin`: everything a viewer sees, plus the
  audit log and (see below) the data-policy page, minus every mutation — the read-only oversight
  role a compliance function occupies. `Settings → Audit` and `Settings → Data policy` are now
  their own sub-pages (out of what used to be folded into Users) so an auditor's Settings nav
  shows only those two.
- **Read-access audit trail.** For a tool whose job is watching people, *who looked at whom* is
  now itself on the record: viewing a client's activity, running a targeted event search
  (`?search=`/`?client_ip=`/`?domain=`/`?user=` — a bare range browse isn't logged, neither is the
  WebSocket-down polling fallback that would otherwise re-issue the same query every ~10s), and
  opening a per-actor analytics drill-down each write an audit entry. Repeats within 5 minutes
  (paging, re-opening the same view) collapse into one entry. Best-effort: a failure to log an
  access is a warning, not a 500 — the read still succeeds.
- **Data policy page** (`Settings → Data policy`, admin + auditor): a plain-language, always-
  current statement of what this deployment collects per request, every retention window actually
  in effect, and whether archiving is on/encrypted — assembled from live settings, not hand-written
  prose that can drift from reality. `DATA_PROCESSING_PURPOSE` / `DATA_CONTROLLER` state the
  configured purpose and controller (blank by default, rendered as "not configured" rather than a
  guess).
- **Signed, offline-verifiable exports.** Set `EXPORT_SIGNING_PRIVATE_KEY` and every finished
  export's manifest (range, filters, row/byte counts, content hash) is signed with Ed25519. A copy
  handed to a third party — legal, compliance, anyone with no login to this system — can be proven
  authentic with the new standalone `backend/scripts/verify_export.py`: no network access back
  here, just the export file, its downloaded manifest, and the published public key. Unsigned
  (key unset) exports are unaffected — still checksummed as before, just without a signature.
- **Subject-access dossier.** `GET /api/subject-access/dossier` (admin-only; a "Dossier" button on
  the Analytics → Who actor sheet) assembles everything this deployment currently knows about one
  client IP or user — activity, categories, top/denied domains, first/last seen, watchlist status —
  into a single document, signed the same way an export manifest is when `EXPORT_SIGNING_PRIVATE_KEY`
  is set. Built entirely from existing aggregates (the same ones the Who actor drill-down and the
  watchlist already read), not a new raw-data scan. Every generation is its own audit entry
  (`SUBJECT_DOSSIER_EXPORTED`) — deliberately not deduplicated like the other read-access actions,
  since producing a dossier is always a deliberate act.
- Corrected `ARCHITECTURE.md`'s frontend-design section: the accent color has been user-selectable
  (amber/azure/violet, `ThemeSwitcher`) for a while, not hardcoded amber as it still claimed —
  emerald/red stay the only two semantically-fixed colors.
- README's "Multi-branch deployment" documented only the rsyslog+TLS path; the simpler SSH-pull
  alternative (`deploy/systemd/squid-ssh-stream@.service`, already shipped and self-documented)
  had no pointer from there, so a reader would default to standing up a CA and per-branch certs
  without knowing a no-TLS-setup option existed. Added a pointer, with the tradeoff.

### Changed

- **The `raw_events` retention window is now admin-tunable** at **Settings →
  Retention** (`GET/PUT /api/retention-settings`, admin only), instead of
  needing a redeploy. `RETENTION_DAYS_RAW_EVENTS` seeds it once; after that
  the DB row wins. Lowering it confirms first (the next purge permanently
  deletes the now-out-of-window rows). The same page adds
  `halt_purge_if_archive_lag_days` (the L9 audit fix): when set,
  `RetentionJob` skips the `raw_events` purge for any cycle where the
  freshest archive across all branches is older than that, and alerts —
  so a broken archiving job can't silently take per-request detail down
  with it. Off by default. The other retention windows stay env-only.
- **Analytics → Branches: the 0–100 "risk score" is gone.** It was an
  uncalibrated blend of five signals with arbitrary weights — the code
  already carried a disclaimer saying not to report it as a number. The
  Branches tab now shows those five signals raw (blocked ratio,
  sensitive-traffic share, anomaly count, quota breaches,
  uncategorized-domain count) in one sortable table, so you pick the lens
  and there's no composite implying precision the inputs don't have.
  `GET /api/analytics/branch-risk` → `branch-signals` (new shape); the
  `RISK_MODEL` env var and `RiskModelConfig` are removed.
- **Analytics → Overview gained two glances it was missing.** A **Recent
  anomalies** panel (the 5 latest `AnomalyEvent`s, branch-scoped to the
  page filter) — until now the landing view of the Analytics section gave
  no hint that anything abnormal had happened; you had to already be on the
  Dashboard. And, when more than one branch is configured, a **Requests by
  branch** strip — the fastest place to spot a branch that has gone quiet
  (0 requests in the window is flagged), which is exactly the failure that
  went unnoticed for two days when one branch's log feed silently stopped.
  `useRecentInsights` / `InsightsPanel` gained optional `limit` and
  `branch`; the Dashboard's usage is unchanged.
- **Analytics → Traffic trimmed to the signals that get acted on.** The tab
  had ~14 breakdowns; the HTTP-methods panel (CONNECT dominates on HTTPS,
  rarely actionable), the request-hierarchy panel (already auto-hidden on a
  single-parent Squid), and the status-codes panel (its 403/407 split
  already lives on the Blocks tab; the status-class bars were low-signal)
  are gone, along with the niche tunnel-ratio tile. What's left, reordered:
  the category/time trend (now first), the result-code mix over time with
  cache-hit and denied ratios, response-time percentiles, and the activity
  heatmap. `GET /api/analytics/http-breakdown` and `/api/analytics/hierarchy`
  are removed with them (the `http_`/`hierarchy_minute_aggregates` tables
  are still written, just not surfaced — a future view can read them).
- **CI now runs a dependency vulnerability scan** (audit finding L5):
  `pip-audit` on the backend and `npm audit --audit-level=high` on the
  frontend — a known advisory in a real dependency fails the build rather
  than only surfacing as an unmerged Dependabot PR. The frontend's
  pre-existing advisories (`undici` via `jsdom` and the `shadcn` CLI,
  `postcss`, `qs`) were cleared with `npm audit fix` (transitive lockfile
  bumps only, no direct-dependency changes).
- **Baseline hardening from the project audit:**
  - Every API response now carries `X-Content-Type-Options: nosniff`,
    `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and
    `Cache-Control: no-store` (an endpoint that is safe to cache can still
    set its own first). Previously the API relied entirely on the frontend
    nginx, which never sees the export / share-link / `/metrics` responses
    the API serves directly.
  - `422` validation errors no longer echo the submitted value back —
    only `loc`, `msg`, `type` — so a malformed body on an auth route can't
    reflect a credential fragment.
  - Production config now also rejects a `JWT_SECRET` under 32 characters
    and a `CORS_ORIGINS` containing `"*"` (which, with
    `allow_credentials=True`, would let any site call the API
    authenticated).
  - `X-Request-ID` from the client is stripped of CR/LF and capped at 128
    chars before it reaches a log record or the response.
- **A demote, branch reassignment, or password reset now ends the account's
  sessions immediately** instead of leaving already-issued access tokens
  valid for the rest of their `ACCESS_TOKEN_EXPIRE_MINUTES` window. Users
  gain a `token_version` column stamped into every access token as a `tv`
  claim; `get_current_user` now reads the account off the database each
  request (the app is a dashboard, not a high-QPS API) and rejects a token
  whose `tv` has moved on, or whose account is gone — and it takes `role`
  and `branch` from the live row, so a scope change lands on the next
  request. `user_service.update_role` / `update_branch` / `reset_password`
  bump `token_version`; the `/ws/live` periodic re-check honours it too. A
  token minted before the column existed carries no `tv` and is
  grandfathered (still checked for the user existing) until it expires.

### Fixed

- **Docker `db-backup` loop lost a whole day on any transient failure.** It ran `pg_dump`
  blind — if Postgres was mid-restart at that instant the cycle failed with "connection
  refused" — and then slept the full `BACKUP_INTERVAL_SECONDS` (a day) before trying again, so a
  momentary blip meant no backup until the next scheduled run. It also drifted: every container
  restart reset the sleep clock, and a slow dump pushed the next one later each day. Now it waits
  (`pg_isready`, up to `BACKUP_WAIT_MAX_SECONDS`) for Postgres to accept connections first,
  retries after `BACKUP_RETRY_SECONDS` (default 10 min) rather than a day on failure, alerts on
  the first failure and then roughly hourly while it stays broken (not once and then silence),
  and — with the new optional `BACKUP_AT_HOUR` — pins the daily run to a fixed UTC hour so it
  doesn't drift across restarts. The bare-metal `backup_database.py` path was unaffected (its
  systemd timer already handles scheduling and catch-up).
- **Analytics → Blocks: denial-reason split double-counted auth challenges.** On an
  auth-enabled deployment every unauthenticated request is logged `TCP_DENIED/407`; folding
  `TCP_DENIED` into "ACL denied" both mislabelled those as ACL denies and counted them a second
  time in `total_denied` (which could then be ~2× the real blocked count). The split is now keyed
  off the disjoint `403` / `407` status codes, so `acl_denied + proxy_auth + other_blocked`
  reconciles exactly with blocked requests.
- **Watchlist matched a lower-cased value against non-lower-cased log data.** A watched domain or
  user with any uppercase (`Evil.example`, `Alice`) never fired. Domain/user matches are now
  case-insensitive.
- **Watchlist could miss a hit if a check run was delayed** — the lookback window is now two
  intervals wide (the per-target cooldown still dedupes), so a slow run can't leave an uncovered
  gap.
- **Analytics → Who: the leaderboard silently dropped unauthenticated traffic** on a
  partial-auth deployment. It now reports the unattributed request count so the rows visibly
  don't have to reconcile with the Overview totals; "first/last seen" is relabelled "first/last
  active (in range)" since it was always range-scoped.
- **Analytics → Who: "new this period"** looked back only one window before the range, flagging a
  long-time user who'd merely had a gap (a weekend) as new; it now checks first-seen across the
  full retained history.
- **Analytics → Branches risk:** the "sensitive traffic" signal divided by *all* bytes including
  domain-less CONNECT tunnels, deflating the ratio on HTTPS-heavy deployments; it now divides by
  domain-attributed bytes.

### Added

- **Settings → System health** (`GET /api/system-health`, admin/auditor).
  One operational snapshot: backup status (last success, size, stale flag)
  and off-site replication status from the jobs' own `backup.json` /
  `offsite.json` (shared `JOB_STATUS_DIR` volume); database size + top
  table sizes + `raw_events` window and 24h row growth; disk free; per-
  branch ingestion (last event time, parse-failure rate, tailer liveness);
  every background job's health (alive / last error / consecutive
  failures); and the recent operational-failure log. Every
  `notify_operator_failure()` now also persists a `system_events` row
  (migration `c5d8e1f3a92b`, pruned after `RETENTION_DAYS_SYSTEM_EVENTS`),
  so a failure is on the record even with no `OPS_ALERT_WEBHOOK_URL` set.
- **The audit log is now tamper-evident** (audit finding M1). Every
  `audit_log_entries` row stores `entry_hash` — SHA-256 over its own
  immutable fields plus the previous entry's `entry_hash` — so any row
  altered, inserted, or removed by someone with database access breaks the
  chain from that point on instead of changing history silently.
  `GET /api/audit-log/verify` (admin/auditor) and
  `backend/scripts/verify_audit_chain.py` (offline, DB access only) walk
  the chain and report the first break. Existing rows are backfilled by
  the migration. Pair it with `REVOKE UPDATE, DELETE ON audit_log_entries`
  on Postgres — the app only ever inserts there.
- **Off-site copies.** `backend/scripts/offsite_sync.py` (bare-metal) and the `db-offsite`
  service in `docker-compose.yml` push both the raw-event archives and the database backups to a
  [restic](https://restic.net) repository on storage that isn't this host — `sftp:`, `s3:`/
  S3-compatible, `b2:`, `rclone:`, or a restic REST server. Until now the archives and the
  `pg_dump`/SQLite backups both landed on the same disk as the live database, so a lost disk/VM
  took every copy with it. The repository is encrypted end-to-end (the `pg_dump` files aren't at
  rest otherwise), deduplicated, and pruned with a grandfather-father-son policy
  (`OFFSITE_KEEP_DAILY`/`_WEEKLY`/`_MONTHLY`) independent of the local retention. Inert until
  `OFFSITE_RESTIC_REPOSITORY` and a passphrase are set. Weekly `restic check` verifies the remote
  repo is still restorable; a failed sync or check posts to `OPS_ALERT_WEBHOOK_URL`
  (`source: offsite`). Systemd units:
  `deploy/systemd/squid-dashboard-offsite{,-check}.{service,timer}`.
- **Watchlist.** Flag a client IP, domain or proxy-auth user (per branch or fleet-wide) at
  **Settings → Watchlist**. A background job raises an anomaly — which then flows through the
  existing webhook/Telegram alert channels and shows in "Recent anomalies" — the next time a
  watched target is active, subject to a cooldown (`WATCHLIST_ALERT_COOLDOWN_SECONDS`). Runs off
  the per-minute client/domain aggregates, not a raw-event scan.
- **Squid config advisor** on the Analytics Overview tab: heuristic checks over the last 24h of
  aggregates for the misconfigurations that quietly make a Squid deployment useless — no caching,
  no proxy auth, nothing ever denied, sensitive categories allowed through, one domain dominating
  all traffic. The panel only appears when there's a finding.
- **Analytics — Squid operations views.** The section grew from 4 to 5 tabs and became a full
  operational picture, not just a usage summary:
  - **Who** — a per-user (or, without proxy auth, per-client-IP) leaderboard: requests, bytes,
    blocked share, top category, busiest hour; click a row for a drill-down (hour-of-day activity,
    category split, top domains, denied domains, first/last seen). Plus a "new this period" list
    of users / client IPs / domains seen for the first time versus the preceding window.
  - **Traffic & cache** — Squid result-code (`%Ss`) mix over time, request- and byte-level cache
    hit rate, deny/tunnel share, HTTP method and status-class breakdown (403/407/5xx called out),
    where requests actually resolved (hierarchy code), and an approximate p50/p95/p99 response-time
    curve from a per-minute latency histogram. The category trend and activity heatmap moved here.
  - **Blocks** — denials over time split by reason (ACL forbid vs. proxy-auth vs. other), with the
    top blocked domains, categories and repeat-offender clients.
  - **Branches** — now also shows per-branch log-ingestion health (tailer alive, parse-failure
    rate, aggregator backlog) alongside the risk score.
- **Four new per-minute aggregate tables** (`result_code_`, `http_`, `hierarchy_`,
  `user_category_minute_aggregates`) plus a six-band response-time histogram on `minute_aggregates`,
  all populated in the existing `Aggregator.flush()` pass — so the operations views run off
  aggregates, not per-request scans, at any traffic volume. `RETENTION_DAYS_OPS_AGGREGATES`
  (default 90) ages them out on their own, shorter schedule.

## [0.3.0] - 2026-09-04

### Added

- **Analytics section** (`/analytics`, new top-level nav item, visible to every role) — four
  sub-views behind one shared range/branch filter:
  - **Overview** — every headline metric for the selected range next to the equal-length range
    before it (delta %), top categories/domains/blocked-domains, and the categories that moved the
    most by volume.
  - **Branches** — a per-branch **risk score** (0–100, banded low/medium/high) blended from five
    weighted signals (blocked-traffic share, sensitive-category traffic, detected anomalies,
    data-quota breaches, high-traffic uncategorized domains), each row expandable to its per-signal
    breakdown; plus an allowed-vs-blocked bar chart and a full per-branch breakdown table.
  - **Categories** — a stacked-area traffic-by-category trend (data or requests, hourly or daily)
    and the biggest movers vs. the previous period.
  - **Activity map** — an hour × weekday heatmap of request volume, in the viewer's local timezone,
    with an all-traffic / blocked-only toggle.
- New read-only endpoints under `/api/analytics/`: `overview`, `category-trend`, `branch-breakdown`,
  `branch-risk`, `activity-heatmap`. All branch-scoped the same way the rest of the read API is
  (a branch-restricted account only ever sees its own branch). No new database tables — every
  number is computed from the existing minute/domain aggregates, `anomaly_events` and
  `alert_settings`.
- **`RISK_MODEL`** config (JSON object, env-overridable) — the risk score's weights, normalization
  ceilings and band thresholds are tunable rather than hardcoded; the shipped defaults are a
  documented starting point, not a calibrated truth.
- **`CATEGORY_TREND_MAX_BUCKETS`** config — an hourly category-trend request over a very wide window
  is automatically coarsened to daily (the response reports the granularity actually used) rather
  than returning thousands of points.

## [0.2.0] - 2026-08-26

### Added

- **TOTP two-factor authentication** — optional, self-service, available to any role. Enable/disable
  from the account menu; backup recovery codes issued on setup.
- **Telegram alerting** — a second delivery channel for high-severity anomalies alongside the
  existing webhook, gated by the same `ALERT_MIN_SEVERITY`.
- **Telegram pairing-code linking** — connecting a branch's (or the super-admin's) Telegram chat no
  longer requires manually looking up a raw numeric chat ID. Click "Connect Telegram", send the
  6-digit code shown to the bot, and the chat links automatically (a background poller resolves it,
  replying in Uzbek). 10-minute code expiry; a new code invalidates the previous pending one.
- **Super-admin Telegram chat** is now DB-backed and editable from a new Settings sub-page
  (unrestricted admins only) — `TELEGRAM_SUPER_ADMIN_CHAT_ID` still works as a fallback when unset.
- **CSV bulk import/export for domain category overrides** — export current overrides as a
  `domain,category` CSV, edit in a spreadsheet, re-import.
- **Cache hit-rate summary card** on the dashboard.
- **`mypy` strict type-checking**, wired into CI alongside `pytest`/`ruff`.
- **Full anomaly localization (uz/ru/en)** — all 8 anomaly types (previously only 4 of 8) now
  render in the user's selected UI language in "Recent anomalies" and the Insights panel, instead
  of falling back to English text.
- `backend/scripts/domain_traffic_report.py` for manual domain-categorization review against a real
  deployment's traffic.

### Changed

- **Settings** split into five focused sub-pages (General, Users, Categories & alerts, Export,
  and the new Telegram page) instead of one long scroll.
- Domain-category CSV import now applies as **one batched database write plus a single summary
  audit entry**, instead of one round trip and one audit row per row — removes a real timeout risk
  on a large import.
- Known-hostname domain-category inference expanded twice against real traffic samples (~175 base
  domains added total: enterprise IT infrastructure, dev/security tooling, regional gov/bank/
  education portals); malformed/non-hostname CONNECT traffic is now rejected instead of silently
  polluting domain-based stats.
- A branch-scoped admin's user-management forms no longer offer "All branches" (the server always
  substituted their own branch anyway; the control now reflects that).

### Fixed

- Cache hit-rate card no longer shows a misleading **"0%"** when there's no cacheable traffic in
  the selected range — renders a dash instead.
- `get_client_summary` no longer reports the wrong "latest" user/branch for a shared/NAT'd client IP
  (was picking alphabetically-greatest, not most-recently-seen).
- **Log tailer**: fixed a silent-data-loss window where the read position was persisted to disk
  before the aggregator had durably flushed the corresponding events — an unclean restart in that
  window meant those events were gone for good. Now only persists once a flush actually commits.
- UT1 blacklist category files are now written atomically (temp file + rename) — a crash or
  disk-full mid-write used to truncate a previously-good file in place.

### Security

- Domain-category CSV export escapes leading spreadsheet-formula-trigger characters (`=`, `+`, `-`,
  `@`) so a planted domain can't execute as a formula when the export is opened directly in
  Excel/Sheets; import reverses the escaping losslessly.
