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

if [ -f "$OVERRIDE" ] && grep -q "extra_hosts:" "$OVERRIDE"; then
  echo "[1/2] Removing leftover 'build: extra_hosts:' block(s) from $OVERRIDE"
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
  echo "[1/2] No leftover extra_hosts block found, nothing to clean"
fi

echo "[2/2] Building frontend and backend through the configured proxy (.env HTTP_PROXY/HTTPS_PROXY, not bypassed)"
docker compose build frontend backend

echo
echo "Done. Now:"
echo "  docker compose up -d"
