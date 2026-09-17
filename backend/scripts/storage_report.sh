#!/usr/bin/env bash
#
# Full storage report for the VM: where every GB is going -- the repo tree,
# ssh-logs, archives, the Postgres database (per table + per index + per
# branch), Docker (images, volumes, build cache), container logs, journald.
# Read-only. Some rows need root for exact sizes; run with `sudo` for the
# complete picture, otherwise those fall back to an estimate or a note.
#
#   bash backend/scripts/storage_report.sh
#   sudo bash backend/scripts/storage_report.sh      # more complete
#
set -u

cd "$(dirname "$0")/../.."
REPO="$(pwd)"

DC="docker compose"
docker compose version >/dev/null 2>&1 || DC="docker-compose"
PSQL="$DC exec -T postgres psql -U squid -d squid_dashboard"
PSQLQ="$DC exec -T postgres psql -U squid -d squid_dashboard -qAt"

hr()  { printf '\n=================== %s ===================\n' "$1"; }
sub() { printf '\n--- %s ---\n' "$1"; }
root_ok() { [ "$(id -u)" -eq 0 ]; }

# ---------------------------------------------------------------- overview
hr "1. DISK OVERVIEW"
df -h / 2>/dev/null | grep -v '^Filesystem\|tmpfs' || df -h /
echo
echo "biggest directories under /  (may take a moment):"
if root_ok; then
    du -x -h -d1 / 2>/dev/null | sort -h | tail -15
else
    echo "(run with sudo for the / breakdown)"
    du -h -d1 "$HOME" 2>/dev/null | sort -h | tail -15
fi

# ---------------------------------------------------------------- repo
hr "2. REPO TREE  ($REPO)"
du -h -d1 "$REPO" 2>/dev/null | sort -h

sub "ssh-logs/  (per branch, then per file)"
if [ -d "$REPO/ssh-logs" ]; then
    for b in $(ls "$REPO"/ssh-logs/*.log 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.log$//'); do
        printf '  %-14s %s\n' "$b" "$(du -ch "$REPO"/ssh-logs/"$b".log* 2>/dev/null | tail -1 | cut -f1)"
    done
    echo
    ls -lhS "$REPO"/ssh-logs/ 2>/dev/null
else
    echo "(no ssh-logs dir)"
fi

sub "archives/  (per file)"
if [ -d "$REPO/archives" ]; then
    du -ch "$REPO"/archives/* 2>/dev/null | tail -1
    ls -lhS "$REPO"/archives/ 2>/dev/null
else
    echo "(no archives dir)"
fi

sub "stray files in repo root"
find "$REPO" -maxdepth 1 -type f -size +1M -exec ls -lh {} \; 2>/dev/null

# ---------------------------------------------------------------- database
hr "3. POSTGRES DATABASE"
$PSQLQ -c "SELECT pg_size_pretty(pg_database_size('squid_dashboard'));" 2>/dev/null \
    | sed 's/^/total database size: /'

sub "per table  (heap + indexes + toast)"
$PSQL -c "
SELECT relname AS table,
       pg_size_pretty(pg_total_relation_size(c.oid))                      AS total,
       pg_size_pretty(pg_relation_size(c.oid))                            AS heap,
       pg_size_pretty(pg_total_relation_size(c.oid) - pg_relation_size(c.oid)) AS idx_toast
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname = 'public'
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 20;" 2>/dev/null

sub "biggest indexes"
$PSQL -c "
SELECT indexrelid::regclass AS index, indrelid::regclass AS on_table,
       pg_size_pretty(pg_relation_size(indexrelid))       AS size,
       CASE WHEN indisvalid THEN '' ELSE 'INVALID' END    AS state
FROM pg_index
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 15;" 2>/dev/null

sub "raw_events by branch  (rows, date span, est. size)"
$PSQL -c "
SELECT branch,
       count(*)                                            AS rows,
       min(timestamp)::date                                AS oldest,
       max(timestamp)::date                                AS newest,
       pg_size_pretty(
         (pg_relation_size('raw_events'::regclass)::numeric
          * count(*) / NULLIF((SELECT count(*) FROM raw_events),0))::bigint) AS approx_heap
FROM raw_events GROUP BY branch ORDER BY branch;" 2>/dev/null

sub "dead rows / bloat (needs VACUUM if n_dead_tup is high)"
$PSQL -c "
SELECT relname, n_live_tup AS live, n_dead_tup AS dead,
       last_autovacuum, last_vacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC LIMIT 10;" 2>/dev/null

# ---------------------------------------------------------------- docker
hr "4. DOCKER"
$DC system df 2>/dev/null
sub "volumes (detailed)"
docker system df -v 2>/dev/null | sed -n '/Local Volumes space usage/,/^$/p'
sub "images"
docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' 2>/dev/null | head -20

sub "container json logs"
if root_ok; then
    du -sh /var/lib/docker/containers/*/ 2>/dev/null | sort -h
    echo "total: $(du -ch /var/lib/docker/containers/*/*-json.log 2>/dev/null | tail -1 | cut -f1)"
else
    echo "(run with sudo to size /var/lib/docker/containers)"
fi

sub "docker volumes on disk"
if root_ok; then
    du -sh /var/lib/docker/volumes/*/ 2>/dev/null | sort -h | tail -15
else
    echo "(run with sudo to size /var/lib/docker/volumes)"
fi

# ---------------------------------------------------------------- system
hr "5. SYSTEM LOGS"
if command -v journalctl >/dev/null 2>&1; then
    journalctl --disk-usage 2>/dev/null
fi
if root_ok; then
    du -sh /var/log 2>/dev/null
    du -h -d1 /var/log 2>/dev/null | sort -h | tail -10
else
    echo "(run with sudo to size /var/log)"
fi

hr "DONE -- paste all of the above"
