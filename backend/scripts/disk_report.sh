#!/usr/bin/env bash
#
# One-shot disk + DB health report for the VM, and -- if there's headroom
# and they're not all built yet -- kicks off the search trigram indexes in
# the background. Read-only except for that last optional step.
#
#   bash backend/scripts/disk_report.sh
#
# The index build (if started) runs detached; watch it with
#   tail -f /tmp/trgm.log

set -u

cd "$(dirname "$0")/../.."

DC="docker compose"
docker compose version >/dev/null 2>&1 || DC="docker-compose"
PSQL="$DC exec -T postgres psql -U squid -d squid_dashboard -qAt"
PSQL_TBL="$DC exec -T postgres psql -U squid -d squid_dashboard"

# Space that must be free (GB) before auto-starting the index build.
MIN_FREE_GB_FOR_INDEX=15

hr() { printf '\n============================== %s ==============================\n' "$1"; }

hr "1. DISK"
df -h / /var 2>/dev/null | grep -v tmpfs
echo
$DC system df

hr "2. POSTGRES / BACKEND HEALTH"
if $PSQL -c "select now();" 2>/dev/null | grep -q .; then
    echo "postgres: responding OK"
else
    echo "postgres: NOT responding to a simple query -- see logs below"
fi
echo
echo "--- postgres log (errors only, last 40) ---"
$DC logs postgres --tail 400 2>/dev/null | grep -iE "ERROR|FATAL|PANIC|no space|could not|shutting down|recovery" | tail -40 \
    || echo "(no error lines)"
echo
echo "--- backend log (last 20) ---"
$DC logs backend --tail 20 2>/dev/null || echo "(backend not running?)"

hr "3. FILES ON DISK"
du -sh ssh-logs archives access.log docs 2>/dev/null | sort -h
echo
echo "--- ssh-logs (biggest first) ---"
ls -lhS ssh-logs/ 2>/dev/null | head -30
echo
echo "--- archives (biggest first) ---"
ls -lhS archives/ 2>/dev/null

hr "4. DATABASE SIZE"
$PSQL_TBL -c "SELECT relname AS table, pg_size_pretty(pg_total_relation_size(oid)) AS total
              FROM pg_class WHERE relkind='r'
              ORDER BY pg_total_relation_size(oid) DESC LIMIT 15;"
echo
$PSQL_TBL -c "SELECT branch, count(*) AS rows,
                     min(timestamp)::date AS oldest, max(timestamp)::date AS newest
              FROM raw_events GROUP BY branch ORDER BY branch;"
echo
echo "--- docker volumes ---"
$DC system df -v 2>/dev/null | sed -n '/Local Volumes/,/^$/p'

hr "5. SEARCH TRIGRAM INDEXES"
$PSQL_TBL -c "SELECT c.relname AS index, i.indisvalid AS valid,
                     pg_size_pretty(pg_relation_size(c.oid)) AS size
              FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
              WHERE c.relname LIKE '%trgm' ORDER BY 1;"

valid_count="$($PSQL -c "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname LIKE '%trgm' AND i.indisvalid;" 2>/dev/null | tr -dc '0-9')"
valid_count="${valid_count:-0}"
free_gb="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
free_gb="${free_gb:-0}"
echo
echo "valid trgm indexes: ${valid_count}/9   |   free space: ${free_gb} GB"

if [ "$valid_count" -ge 9 ]; then
    echo "-> all 9 built. Nothing to do."
elif pgrep -f build_search_indexes.sh >/dev/null; then
    echo "-> a build is already running (pid $(pgrep -f build_search_indexes.sh | tr '\n' ' ')). Watch: tail -f /tmp/trgm.log"
elif [ "$free_gb" -lt "$MIN_FREE_GB_FOR_INDEX" ]; then
    echo "-> only ${free_gb} GB free (< ${MIN_FREE_GB_FOR_INDEX}). NOT starting the build -- free disk first."
else
    echo "-> starting the remaining index build in the background..."
    nohup bash backend/scripts/build_search_indexes.sh > /tmp/trgm.log 2>&1 &
    echo "   started (pid $!). Watch: tail -f /tmp/trgm.log"
fi

hr "DONE"
