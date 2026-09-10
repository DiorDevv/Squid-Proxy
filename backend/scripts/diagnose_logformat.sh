#!/usr/bin/env bash
#
# Read-only diagnostic. Gathers everything needed to finalise the Squid
# access.log parser for the upload/download (%>st / %<st) work: how many
# fields each branch's lines have, whether the clock is epoch or
# Apache-style, the order of the two byte columns, what migration the DB is
# on, and whether any lines are currently failing to parse.
#
# Run from the repo root on the VM:
#     bash backend/scripts/diagnose_logformat.sh
#
# Nothing here writes anything. If the streamed log files are root-owned it
# will use `sudo tail` (you may be prompted for a password once).

set -u

sep() { printf '\n========================= %s =========================\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

DC="docker compose"
have docker || DC=""
if [ -n "$DC" ] && ! docker compose version >/dev/null 2>&1; then
  have docker-compose && DC="docker-compose" || DC=""
fi

sep "0. where am I / repo state"
pwd
git rev-parse --abbrev-ref HEAD 2>/dev/null && git log --oneline -1 2>/dev/null || echo "(not a git repo in this dir)"
if [ ! -f docker-compose.yml ] && [ ! -f docker-compose.override.yml ]; then
  echo
  echo "!! No docker-compose*.yml here. cd to the repo root (e.g. ~/squid-watch) and re-run."
fi

sep "1. configured LOG_SOURCES (which branches, which files)"
for f in docker-compose.override.yml docker-compose.yml .env; do
  [ -f "$f" ] && { echo "--- $f ---"; grep -n -i "LOG_SOURCE" "$f" || echo "(no LOG_SOURCE line)"; }
done
if [ -n "$DC" ]; then
  echo "--- docker compose config (resolved) ---"
  $DC config 2>/dev/null | grep -i -A2 "LOG_SOURCE" || echo "(none in resolved config)"
fi

sep "2. migration the database is currently on"
if [ -n "$DC" ]; then
  $DC exec -T backend alembic current 2>/dev/null \
    || $DC run --rm backend alembic current 2>/dev/null \
    || echo "(could not run 'alembic current' -- is the backend service up?)"
else
  echo "(docker compose not found)"
fi

sep "3. locate the streamed log files"
LOGDIR=""
for d in ssh-logs logs /data/squid-logs; do
  [ -d "$d" ] && { LOGDIR="$d"; break; }
done
if [ -z "$LOGDIR" ]; then
  cand=$(find . -maxdepth 4 -name '*.log' \( -path '*ssh-logs*' -o -path '*squid-logs*' \) 2>/dev/null | head -1)
  [ -n "$cand" ] && LOGDIR=$(dirname "$cand")
fi
if [ -z "$LOGDIR" ]; then
  echo "!! Could not find a log directory. Set it by hand:"
  echo "     LOGDIR=/path/to/ssh-logs bash backend/scripts/diagnose_logformat.sh"
  LOGDIR="${LOGDIR:-}"
fi
echo "using LOGDIR = ${LOGDIR:-<none>}"
[ -n "$LOGDIR" ] && ls -la "$LOGDIR" 2>/dev/null

readlog() {  # readlog <file> <n>
  sudo tail -n "${2:-6}" "$1" 2>/dev/null || tail -n "${2:-6}" "$1" 2>/dev/null || echo "(unreadable: $1 -- try running this script with sudo)"
}

if [ -n "$LOGDIR" ]; then
  shopt -s nullglob 2>/dev/null || true
  for f in "$LOGDIR"/*.log; do
    [ -f "$f" ] || continue
    sep "BRANCH FILE: $f"

    echo "-- last 6 lines --"
    readlog "$f" 6

    echo
    echo "-- field count over the last 300 lines (count x fields) --"
    echo "   NOTE: an Apache-style clock has a space in it, so it inflates the count by 1"
    readlog "$f" 300 | awk 'NF{print NF}' | sort -n | uniq -c

    echo
    echo "-- first token of the newest line (clock style) --"
    readlog "$f" 1 | awk '{print "   " $1}'
    echo "   epoch  = 1788959760.199        Apache = 03/Sep/2026:15:22:46"

    echo
    echo "-- a denied CONNECT line (shows the two size columns after the /403) --"
    readlog "$f" 5000 | grep -m1 -E 'TCP_DENIED/403[[:space:]].*[[:space:]]CONNECT[[:space:]]' \
      || echo "   (no denied CONNECT in the last 5000 lines)"
  done
fi

sep "4. backend parse warnings in the last 20 min"
if [ -n "$DC" ]; then
  $DC logs backend --since 20m 2>/dev/null | grep -i -E "fields, expected|skipping line|Invalid (timestamp|client IP)|bytes_received" | tail -40 \
    || echo "(none -- healthy, or backend logs unavailable)"
else
  echo "(docker compose not found)"
fi

sep "DONE -- copy everything above and paste it back"
