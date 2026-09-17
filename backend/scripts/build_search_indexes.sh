#!/usr/bin/env bash
#
# Builds the GIN trigram indexes that make free-text search index-backed
# (see build_search_indexes.sql). Runs them CONCURRENTLY, so the app can
# stay up the whole time. Run once after deploying c9e4b7a15d02 on a DB
# that already has data; safe to re-run.
#
#   bash backend/scripts/build_search_indexes.sh
#
# Each raw_events index takes a few minutes on a large table -- watch
# progress in another shell with:
#   docker compose exec -T postgres psql -U squid -d squid_dashboard -c \
#     "SELECT phase, blocks_done||'/'||blocks_total FROM pg_stat_progress_create_index;"

set -euo pipefail

cd "$(dirname "$0")/../.."

DC="docker compose"
docker compose version >/dev/null 2>&1 || DC="docker-compose"

echo "Building search trigram indexes (CONCURRENTLY -- the app stays up)..."
$DC exec -T postgres psql -U squid -d squid_dashboard -v ON_ERROR_STOP=1 \
    < backend/scripts/build_search_indexes.sql
echo "Done. All 9 *_trgm indexes should be listed above and marked valid."
