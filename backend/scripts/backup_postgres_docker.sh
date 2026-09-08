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
# down -- no `set -e`. Three things the naive "dump; sleep 24h; repeat"
# loop got wrong, all fixed below:
#   1. It ran pg_dump blind. If Postgres was mid-restart at that instant it
#      failed with "connection refused". Now it waits (pg_isready) for the
#      server to accept connections first, up to BACKUP_WAIT_MAX_SECONDS.
#   2. A failed cycle then slept the *full* BACKUP_INTERVAL_SECONDS -- one
#      bad moment cost a whole day with no backup. A failure now retries
#      after BACKUP_RETRY_SECONDS (default 10 min).
#   3. "Daily" drifted: every container restart reset the sleep clock, and
#      a slow dump pushed the next one later each day. A successful cycle
#      now sleeps to a fixed wall-clock target -- BACKUP_AT_HOUR (UTC) if
#      set, otherwise BACKUP_INTERVAL_SECONDS minus however long this
#      cycle already took.

output_dir="${BACKUP_OUTPUT_DIR:-/backups}"
keep_days="${BACKUP_KEEP_DAYS:-30}"
interval_seconds="${BACKUP_INTERVAL_SECONDS:-86400}"
retry_seconds="${BACKUP_RETRY_SECONDS:-600}"
wait_max_seconds="${BACKUP_WAIT_MAX_SECONDS:-300}"
# Optional: pin the daily run to this UTC hour (0-23) so the backup lands
# at the same time every day regardless of restarts. Unset -> fall back to
# a drift-corrected BACKUP_INTERVAL_SECONDS.
backup_at_hour="${BACKUP_AT_HOUR:-}"
# Where to drop a machine-readable status file the backend reads for
# Settings -> System health (a shared read-only volume; see
# docker-compose.yml). This container can't reach Postgres from the
# backend's network and has no app package, so a file is how it reports.
status_dir="${JOB_STATUS_DIR:-/status}"
# Same fallback as app/services/ops_alerting.py's Python side: a
# single-webhook operator sets only ALERT_WEBHOOK_URL and gets it here too.
ops_webhook_url="${OPS_ALERT_WEBHOOK_URL:-${ALERT_WEBHOOK_URL:-}}"

# Rewrite $status_dir/backup.json after every cycle. Args:
#   $1 ok (true|false)  $2 error (empty on success)
#   $3 last dump basename (empty unless this cycle produced one)
#   $4 last dump size in bytes (empty unless known)
# last_success_at is carried across cycles via a marker file so a failed
# cycle's status still shows when the last good backup was.
write_status() {
  st_ok=$1; st_err=$2; st_dump=$3; st_bytes=$4
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$status_dir" 2>/dev/null || return 0
  [ "$st_ok" = "true" ] && printf '%s' "$now" > "$status_dir/.backup_last_success" 2>/dev/null
  last_success=$(cat "$status_dir/.backup_last_success" 2>/dev/null || echo "")
  disk=$(df -PB1 "$output_dir" 2>/dev/null | awk 'NR==2 {print $2 "," $4}')
  disk_total=${disk%,*}
  disk_free=${disk#*,}
  # error strings here are our own controlled literals (no quotes/newlines);
  # strip a stray double-quote defensively anyway.
  st_err=$(printf '%s' "$st_err" | tr -d '"')
  {
    printf '{"updated_at":"%s","ok":%s' "$now" "$st_ok"
    if [ -n "$last_success" ]; then printf ',"last_success_at":"%s"' "$last_success"; else printf ',"last_success_at":null'; fi
    if [ -n "$st_dump" ]; then printf ',"last_dump":"%s"' "$st_dump"; else printf ',"last_dump":null'; fi
    if [ -n "$st_bytes" ] && [ "$st_bytes" != "?" ]; then printf ',"last_dump_bytes":%s' "$st_bytes"; else printf ',"last_dump_bytes":null'; fi
    printf ',"consecutive_failures":%s' "$consecutive_failures"
    if [ -n "$st_err" ]; then printf ',"error":"%s"' "$st_err"; else printf ',"error":null'; fi
    if [ -n "$disk_total" ]; then printf ',"disk_total_bytes":%s,"disk_free_bytes":%s' "$disk_total" "$disk_free"; else printf ',"disk_total_bytes":null,"disk_free_bytes":null'; fi
    printf '}\n'
  } > "$status_dir/backup.json" 2>/dev/null || true
}

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

# Block until Postgres accepts connections, or give up after
# wait_max_seconds. Returns 0 if ready, 1 if it timed out -- the caller
# treats a timeout the same as a failed dump (short retry + alert) rather
# than charging ahead into a pg_dump that can only fail.
wait_for_postgres() {
  waited=0
  while [ "$waited" -lt "$wait_max_seconds" ]; do
    if pg_isready -q; then
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done
  pg_isready -q
}

# Seconds to sleep after a successful backup. With BACKUP_AT_HOUR set,
# that's the time until the next occurrence of that UTC hour (pure
# arithmetic on the current UTC time -- busybox date has no date math).
# Otherwise it's BACKUP_INTERVAL_SECONDS minus how long this cycle took,
# floored at 60s so a dump that overruns the interval can't spin.
sleep_until_next() {
  cycle_elapsed=$1
  if [ -n "$backup_at_hour" ]; then
    now_h=$(date -u +%H)
    now_m=$(date -u +%M)
    now_s=$(date -u +%S)
    # Strip any leading zero so these aren't read as octal.
    now_secs=$(( ${now_h#0} * 3600 + ${now_m#0} * 60 + ${now_s#0} ))
    target_secs=$(( ${backup_at_hour#0} * 3600 ))
    delta=$(( (target_secs - now_secs + 86400) % 86400 ))
    [ "$delta" -eq 0 ] && delta=86400
    echo "$delta"
    return
  fi
  remaining=$(( interval_seconds - cycle_elapsed ))
  [ "$remaining" -lt 60 ] && remaining=60
  echo "$remaining"
}

mkdir -p "$output_dir"
consecutive_failures=0

while true; do
  cycle_start=$(date -u +%s)
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  dest="$output_dir/squid-dashboard-backup-${timestamp}.dump"

  ok=0
  if ! wait_for_postgres; then
    echo "Postgres not accepting connections after ${wait_max_seconds}s -- skipping this cycle" >&2
    reason="Postgres unreachable after ${wait_max_seconds}s"
  elif pg_dump --format=custom --file="$dest"; then
    size=$(stat -c%s "$dest" 2>/dev/null || echo "?")
    echo "Database backup complete: $dest (${size} bytes)"
    ok=1
  else
    # pg_dump can leave a partial file behind before failing -- drop it so
    # it can't be mistaken for a real backup.
    rm -f "$dest"
    reason="pg_dump exited non-zero"
  fi

  # Retention runs every cycle regardless -- it must stay bounded even
  # through a run of failed backups.
  find "$output_dir" -name 'squid-dashboard-backup-*' -mtime "+${keep_days}" -print -delete

  if [ "$ok" -eq 1 ]; then
    consecutive_failures=0
    write_status "true" "" "$(basename "$dest")" "$size"
    cycle_elapsed=$(( $(date -u +%s) - cycle_start ))
    nap=$(sleep_until_next "$cycle_elapsed")
    echo "Next backup in ${nap}s"
    sleep "$nap"
  else
    consecutive_failures=$((consecutive_failures + 1))
    down_for=$(( consecutive_failures * retry_seconds ))
    write_status "false" "$reason" "" ""
    echo "Database backup FAILED (${reason}); attempt #${consecutive_failures}, retrying in ${retry_seconds}s" >&2
    # Alert on the first failure, then roughly hourly while it stays broken
    # -- enough that it isn't forgotten, not so much it floods the channel.
    alert_every=$(( 3600 / retry_seconds ))
    [ "$alert_every" -lt 1 ] && alert_every=1
    if [ "$consecutive_failures" -eq 1 ] || [ $(( consecutive_failures % alert_every )) -eq 0 ]; then
      notify_operator_failure "Database backup has failed ${consecutive_failures}x (~${down_for}s); last reason: ${reason}. Retrying every ${retry_seconds}s."
    fi
    sleep "$retry_seconds"
  fi
done
