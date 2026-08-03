#!/bin/sh
# Docker counterpart to verify_backup_restore.py -- same idea (restore the
# newest backup into a throwaway database, run a minimal sanity query, drop
# it, never touch the real database), but shells out to `pg_restore`/`psql`
# directly since this runs inside the same postgres:16-alpine-based
# environment as backup_postgres_docker.sh, not the Python backend image.
#
# Not wired into a continuously-running service (restoring a full dump on
# every backup cycle isn't cheap) -- run manually or via a weekly cron/host
# scheduler, e.g.:
#   docker compose exec db-backup sh /verify_backup_restore_docker.sh
# See README.md's "Database backups" section.
#
# One failed run must not corrupt anything -- the throwaway database is
# always dropped in the cleanup step below, even on failure.

output_dir="${BACKUP_OUTPUT_DIR:-/backups}"
ops_webhook_url="${OPS_ALERT_WEBHOOK_URL:-${ALERT_WEBHOOK_URL:-}}"
sanity_table="users"

notify_operator_failure() {
  [ -n "$ops_webhook_url" ] || return 0
  message=$1
  wget -q -T 5 -O /dev/null \
    --header='Content-Type: application/json' \
    --post-data="{\"title\":\"Squid Watch operator alert: backup_restore_verify\",\"description\":\"${message}\",\"severity\":\"high\",\"source\":\"backup_restore_verify\",\"generated_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    "$ops_webhook_url" || true
}

fail() {
  echo "Backup restore verification FAILED: $1" >&2
  notify_operator_failure "$1"
  [ -n "$throwaway_db" ] && dropdb --if-exists "$throwaway_db" 2>/dev/null
  exit 1
}

backup_file=$(ls -t "$output_dir"/squid-dashboard-backup-*.dump 2>/dev/null | head -1)
[ -n "$backup_file" ] || fail "No backup files found in $output_dir"

throwaway_db="squid_dashboard_restore_verify_$(date -u +%Y%m%dT%H%M%SZ)"

createdb "$throwaway_db" || fail "Could not create throwaway database $throwaway_db"

if ! pg_restore --dbname="$throwaway_db" --no-owner "$backup_file" 2>/tmp/restore_stderr; then
  fail "pg_restore failed for $backup_file: $(cat /tmp/restore_stderr)"
fi

row_count=$(psql --dbname="$throwaway_db" --tuples-only --command "SELECT count(*) FROM ${sanity_table}" 2>/tmp/sanity_stderr) \
  || fail "Sanity query against $sanity_table failed: $(cat /tmp/sanity_stderr)"

dropdb --if-exists "$throwaway_db"

echo "Backup restore verification succeeded: $backup_file (sanity row count:${row_count})"
