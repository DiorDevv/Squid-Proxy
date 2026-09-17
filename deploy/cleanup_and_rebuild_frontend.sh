#!/bin/bash
# One-shot cleanup + rebuild after today's DNS-bypass detour (reverted --
# see git log). Strips any leftover empty `build: extra_hosts:` block that
# an earlier, now-reverted script may have written into
# docker-compose.override.yml (harmless if there isn't one), then rebuilds
# frontend/backend the correct way: through the configured HTTP_PROXY/
# HTTPS_PROXY in .env, never bypassed -- this VM has no direct internet,
# only proxy egress, so a build only ever succeeds through it.
#
# Run from the repo root: deploy/cleanup_and_rebuild_frontend.sh

set -eu
cd "$(dirname "$0")/.."

OVERRIDE=docker-compose.override.yml

# 0) Self-heal: if the file is present but not even valid YAML/Compose
# config (e.g. a previous edit got cut off mid-heredoc), don't try to
# surgically patch unknown corruption -- back it up and rewrite the known-
# good content instead (this repo's real deployment: the actual Squid log
# bind-mount + the Postgres tuning from earlier today). Only touches the
# file if it's actually broken; a valid file (even with the old extra_hosts
# cruft still in it) is left for step 1 below to handle precisely.
if [ -f "$OVERRIDE" ] && ! docker compose config --quiet 2>/dev/null; then
  backup="${OVERRIDE}.broken-$(date +%Y%m%dT%H%M%S)"
  echo "[1/3] $OVERRIDE isn't valid YAML/Compose config -- backing it up to $backup and restoring known-good content"
  mv "$OVERRIDE" "$backup"
  cat > "$OVERRIDE" << 'EOF'
services:
  backend:
    environment:
      LOG_SOURCES: '[{"branch":"server","path":"/data/squid-logs/server.log"},{"branch":"filial","path":"/data/squid-logs/filial.log"},{"branch":"main","path":"/data/squid-logs/main.log"}]'
    volumes:
      - ./ssh-logs:/data/squid-logs:ro
  postgres:
    command:
      - "postgres"
      - "-c"
      - "shared_buffers=2GB"
      - "-c"
      - "effective_cache_size=3GB"
      - "-c"
      - "max_wal_size=2GB"
EOF
  echo "  restored -- diff against the backup if you had other local changes in it:"
  echo "  diff $backup $OVERRIDE"
fi

if [ -f "$OVERRIDE" ] && grep -q "extra_hosts:" "$OVERRIDE"; then
  echo "[2/3] Removing leftover 'build: extra_hosts:' block(s) from $OVERRIDE"
  python3 - "$OVERRIDE" <<'PYEOF'
import re
import sys

path = sys.argv[1]
text = open(path).read()
# Matches exactly the shape the reverted script left behind:
#     build:
#       extra_hosts:
# with nothing (or resolved host lines) under extra_hosts -- remove the
# whole build: block along with any "- host:ip" lines under it.
pattern = re.compile(
    r"^    build:\n      extra_hosts:\n(?:        - .+\n)*",
    re.MULTILINE,
)
new_text, count = pattern.subn("", text)
if count:
    # A service whose *only* content was the removed block now dangles as
    # "  name:\n" with nothing under it (valid YAML -- null -- but untidy).
    # Drop it too if the next line is another top-level service or EOF.
    new_text = re.sub(r"^  \w+:\n(?=  \w+:\n|\Z)", "", new_text, flags=re.MULTILINE)
    open(path, "w").write(new_text)
    print(f"  removed {count} block(s)")
else:
    print("  nothing matched, left as-is")
PYEOF
else
  echo "[2/3] No leftover extra_hosts block found, nothing to clean"
fi

echo "[3/3] Building frontend and backend through the configured proxy (.env HTTP_PROXY/HTTPS_PROXY, not bypassed)"
docker compose build frontend backend

echo
echo "Done. Now:"
echo "  docker compose up -d"
