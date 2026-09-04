# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

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
