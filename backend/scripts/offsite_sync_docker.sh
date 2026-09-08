#!/bin/sh
# Off-site replication of the local backup + archive files -- the Docker
# counterpart to the db-backup service, one step further out. db-backup
# writes pg_dump files into the db_backup_data volume, on the same disk as
# Postgres itself; this takes those (plus the ./archives bind mount) and
# pushes them to a restic repository that is NOT on this host. See
# scripts/offsite_sync.py's docstring and "Off-site copies" in README.md
# for the what and why -- this is the same logic as a plain
# `while true; sleep` loop so the stock docker-compose deployment gets it
# without a host cron entry.
#
# Runs in the restic/restic image (entrypoint overridden to /bin/sh in
# docker-compose.yml), so `restic` is the container's own pinned binary
# and busybox `wget` is present for the failure webhook.
#
# One failed cycle (repo unreachable, credentials rotated out, a network
# blip) must not kill the loop -- no `set -e`; log, alert, retry next
# cycle.

repo="${RESTIC_REPOSITORY:-${OFFSITE_RESTIC_REPOSITORY:-}}"
interval_seconds="${OFFSITE_INTERVAL_SECONDS:-86400}"
keep_daily="${OFFSITE_KEEP_DAILY:-7}"
keep_weekly="${OFFSITE_KEEP_WEEKLY:-8}"
keep_monthly="${OFFSITE_KEEP_MONTHLY:-12}"
# Run `restic check` once every N cycles (0 disables). Verifying the
# remote repo every day is wasteful; weekly-ish catches a repo going bad
# well before retention would rotate out the last good local backup.
check_every="${OFFSITE_CHECK_EVERY:-7}"
paths="${OFFSITE_PATHS:-/backups /archives}"
# Machine-readable status for the backend's Settings -> System health page
# (shared read-only volume, see docker-compose.yml).
status_dir="${JOB_STATUS_DIR:-/status}"
# Same fallback as app/services/ops_alerting.py: a single-webhook operator
# sets only ALERT_WEBHOOK_URL and still gets these alerts.
ops_webhook_url="${OPS_ALERT_WEBHOOK_URL:-${ALERT_WEBHOOK_URL:-}}"

# offsite.json fields: enabled, last sync/check timestamps + outcomes,
# last error, masked repo. Sync and check outcomes are tracked in files so
# each write reflects the latest of both regardless of which just ran.
_repo_masked() {
  # keep the scheme + host, drop anything that could be a path/secret
  printf '%s' "$repo" | sed -E 's#(^[a-z0-9+]+:[^/]*/[^/]+).*#\1/...#'
}
write_offsite_status() {
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$status_dir" 2>/dev/null || return 0
  ls_at=$(cat "$status_dir/.offsite_sync_at" 2>/dev/null || echo "")
  ls_ok=$(cat "$status_dir/.offsite_sync_ok" 2>/dev/null || echo "")
  lc_at=$(cat "$status_dir/.offsite_check_at" 2>/dev/null || echo "")
  lc_ok=$(cat "$status_dir/.offsite_check_ok" 2>/dev/null || echo "")
  err=$(cat "$status_dir/.offsite_error" 2>/dev/null | tr -d '"' || echo "")
  {
    printf '{"updated_at":"%s","enabled":true,"repo":"%s"' "$now" "$(_repo_masked)"
    if [ -n "$ls_at" ]; then printf ',"last_sync_at":"%s","last_sync_ok":%s' "$ls_at" "${ls_ok:-false}"; else printf ',"last_sync_at":null,"last_sync_ok":null'; fi
    if [ -n "$lc_at" ]; then printf ',"last_check_at":"%s","last_check_ok":%s' "$lc_at" "${lc_ok:-false}"; else printf ',"last_check_at":null,"last_check_ok":null'; fi
    if [ -n "$err" ]; then printf ',"error":"%s"' "$err"; else printf ',"error":null'; fi
    printf '}\n'
  } > "$status_dir/offsite.json" 2>/dev/null || true
}
write_offsite_disabled_status() {
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$status_dir" 2>/dev/null || return 0
  printf '{"updated_at":"%s","enabled":false,"repo":null,"last_sync_at":null,"last_sync_ok":null,"last_check_at":null,"last_check_ok":null,"error":null}\n' \
    "$now" > "$status_dir/offsite.json" 2>/dev/null || true
}

# restic reads these itself; accept the OFFSITE_-prefixed aliases too so
# every off-site setting can live under one prefix in .env.
export RESTIC_REPOSITORY="$repo"
: "${RESTIC_PASSWORD_FILE:=${OFFSITE_RESTIC_PASSWORD_FILE:-}}"
: "${RESTIC_PASSWORD:=${OFFSITE_RESTIC_PASSWORD:-}}"
export RESTIC_PASSWORD_FILE RESTIC_PASSWORD

idle_forever() {
  # Stay running so `docker compose` doesn't treat this as a crash-looping
  # service and back off restarting the rest of the stack's dependents.
  while true; do sleep 86400; done
}

notify_operator_failure() {
  [ -n "$ops_webhook_url" ] || return 0
  message=$1
  wget -q -T 5 -O /dev/null \
    --header='Content-Type: application/json' \
    --post-data="{\"title\":\"Squid Watch operator alert: offsite\",\"description\":\"${message}\",\"severity\":\"high\",\"source\":\"offsite\",\"generated_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    "$ops_webhook_url" || true
}

mkdir -p "$status_dir" 2>/dev/null || true

if [ "${OFFSITE_ENABLED:-}" = "false" ]; then
  echo "OFFSITE_ENABLED=false -- db-offsite service idle by request"
  write_offsite_disabled_status
  idle_forever
fi

if [ -z "$repo" ]; then
  echo "db-offsite: no OFFSITE_RESTIC_REPOSITORY set -- nothing to replicate." >&2
  echo "Set it (and a repo password) in .env, or set OFFSITE_ENABLED=false to silence this." >&2
  write_offsite_disabled_status
  idle_forever
fi

if [ -z "$RESTIC_PASSWORD_FILE" ] && [ -z "$RESTIC_PASSWORD" ]; then
  echo "db-offsite: OFFSITE_RESTIC_REPOSITORY is set but no repo password is." >&2
  echo "Set OFFSITE_RESTIC_PASSWORD or OFFSITE_RESTIC_PASSWORD_FILE in .env." >&2
  write_offsite_disabled_status
  idle_forever
fi

# Create the repo on first run. `restic cat config` succeeds iff the repo
# exists and the password is right; only init when it doesn't.
if ! restic cat config >/dev/null 2>&1; then
  if restic init; then
    echo "Initialised a new restic repository at $repo"
  else
    echo "db-offsite: restic repository not usable and init failed -- check repo URL and credentials." >&2
    notify_operator_failure "Off-site restic repo unreachable and init failed at startup"
  fi
fi

cycle=0
while true; do
  cycle=$((cycle + 1))
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # shellcheck disable=SC2086  # $paths is a space-separated path list, split on purpose
  if restic backup --tag squid-watch $paths; then
    echo "Off-site backup complete: $paths"
    printf '%s' "$now" > "$status_dir/.offsite_sync_at" 2>/dev/null
    printf 'true' > "$status_dir/.offsite_sync_ok" 2>/dev/null
    : > "$status_dir/.offsite_error" 2>/dev/null
    if ! restic forget --prune --tag squid-watch \
        --keep-daily "$keep_daily" --keep-weekly "$keep_weekly" --keep-monthly "$keep_monthly"; then
      echo "Off-site retention (restic forget) FAILED this cycle" >&2
      printf 'restic forget --prune failed' > "$status_dir/.offsite_error" 2>/dev/null
      notify_operator_failure "Off-site retention (restic forget --prune) failed this cycle"
    fi
  else
    echo "Off-site backup FAILED this cycle -- will retry in ${interval_seconds}s" >&2
    printf '%s' "$now" > "$status_dir/.offsite_sync_at" 2>/dev/null
    printf 'false' > "$status_dir/.offsite_sync_ok" 2>/dev/null
    printf 'restic backup failed this cycle' > "$status_dir/.offsite_error" 2>/dev/null
    notify_operator_failure "Off-site backup (restic) FAILED this cycle; will retry in ${interval_seconds}s"
  fi

  if [ "$check_every" -gt 0 ] && [ $((cycle % check_every)) -eq 0 ]; then
    printf '%s' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$status_dir/.offsite_check_at" 2>/dev/null
    if restic check; then
      echo "Off-site repository check passed"
      printf 'true' > "$status_dir/.offsite_check_ok" 2>/dev/null
    else
      echo "Off-site repository check FAILED -- remote copy may not be restorable" >&2
      printf 'false' > "$status_dir/.offsite_check_ok" 2>/dev/null
      printf 'restic check failed -- remote copy may not be restorable' > "$status_dir/.offsite_error" 2>/dev/null
      notify_operator_failure "Off-site restic repository check FAILED -- remote copy may not be restorable"
    fi
  fi

  write_offsite_status
  sleep "$interval_seconds"
done
