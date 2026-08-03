#!/bin/sh
# Backs up the docker-compose Postgres database on a loop -- the Docker
# counterpart to backup_database.py, but deliberately not the same script:
# this runs inside a container built FROM postgres:16-alpine (see
# docker-compose.yml's db-backup service), which guarantees pg_dump exactly
# matches the target server's version without needing Postgres client tools
# installed into the Python backend image (where a generic `apt install
# postgresql-client` could easily resolve to an older major version than
# the server's). Connection info comes from the standard libpq PGHOST/
# PGUSER/PGPASSWORD/PGDATABASE env vars (set in docker-compose.yml,
# mirroring the postgres service's own), so there's no DATABASE_URL to
# parse here either.
#
# One failed cycle (e.g. Postgres mid-restart) must not take the whole loop
# down -- no `set -e`; a failure just gets logged and retried next cycle.

output_dir="${BACKUP_OUTPUT_DIR:-/backups}"
keep_days="${BACKUP_KEEP_DAYS:-30}"
interval_seconds="${BACKUP_INTERVAL_SECONDS:-86400}"
# Same fallback as app/services/ops_alerting.py's Python side: a
# single-webhook operator sets only ALERT_WEBHOOK_URL and gets it here too.
ops_webhook_url="${OPS_ALERT_WEBHOOK_URL:-${ALERT_WEBHOOK_URL:-}}"

# This container has no Python/app package (it's bare postgres:16-alpine),
# so it can't import ops_alerting -- posts the same payload shape directly
# with busybox wget (confirmed present in this base image; curl is not,
# so this deliberately isn't a curl call). Best-effort: `|| true` so a
# webhook hiccup can never take down the backup loop itself.
notify_operator_failure() {
  [ -n "$ops_webhook_url" ] || return 0
  message=$1
  wget -q -T 5 -O /dev/null \
    --header='Content-Type: application/json' \
    --post-data="{\"title\":\"Squid Watch operator alert: backup\",\"description\":\"${message}\",\"severity\":\"high\",\"source\":\"backup\",\"generated_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    "$ops_webhook_url" || true
}

mkdir -p "$output_dir"

while true; do
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  dest="$output_dir/squid-dashboard-backup-${timestamp}.dump"

  if pg_dump --format=custom --file="$dest"; then
    size=$(stat -c%s "$dest" 2>/dev/null || echo "?")
    echo "Database backup complete: $dest (${size} bytes)"
  else
    echo "Database backup FAILED this cycle -- will retry in ${interval_seconds}s" >&2
    rm -f "$dest"
    notify_operator_failure "Database backup FAILED this cycle; will retry in ${interval_seconds}s"
  fi

  find "$output_dir" -name 'squid-dashboard-backup-*' -mtime "+${keep_days}" -print -delete

  sleep "$interval_seconds"
done
