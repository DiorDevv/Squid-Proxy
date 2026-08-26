# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

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
