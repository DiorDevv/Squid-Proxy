#!/bin/bash
# One-shot: applies this session's resource-tuning decisions (higher
# postgres/backend RAM, Postgres shared_buffers/effective_cache_size/
# max_wal_size, balanced cpu_shares already in docker-compose.yml) and
# restarts the stack with them. Safe to re-run: every step is skip-safe,
# and it never overwrites an existing docker-compose.override.yml wholesale
# -- it only appends the postgres tuning block if that file doesn't already
# have one, so a real deployment's LOG_SOURCES/volumes bind-mount survives.
#
# Run this ON THE VM, from the repo root:
#   deploy/tune_resources.sh
#
# Sizing here matches a modest-but-real deployment (a handful of branches,
# tens of GB of raw_events) -- not the README's 30,000-client preset, which
# is considerably larger. Re-tune the numbers below by hand if your load
# looks more like that.

set -eu

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "XATO: .env topilmadi. Avval 'cp .env.example .env' qiling." >&2
  exit 1
fi

set_env() {
  key="$1"; value="$2"
  if grep -q "^${key}=" .env 2>/dev/null; then
    echo "  .env: ${key} allaqachon bor, o'tkazib yuborildi"
  else
    echo "${key}=${value}" >> .env
    echo "  .env: ${key}=${value} qo'shildi"
  fi
}

echo "[1/3] .env resurs sozlamalari"
set_env POSTGRES_MEMORY_LIMIT 4g
set_env POSTGRES_CPU_LIMIT 4
set_env BACKEND_MEMORY_LIMIT 2g

echo "[2/3] docker-compose.override.yml -- Postgres tuning"
if [ -f docker-compose.override.yml ] && grep -q "shared_buffers" docker-compose.override.yml; then
  echo "  allaqachon qo'llangan, o'tkazib yuborildi"
else
  {
    echo "  postgres:"
    echo "    command:"
    echo "      - \"postgres\""
    echo "      - \"-c\""
    echo "      - \"shared_buffers=1GB\""
    echo "      - \"-c\""
    echo "      - \"effective_cache_size=3GB\""
    echo "      - \"-c\""
    echo "      - \"max_wal_size=2GB\""
  } >> docker-compose.override.yml
  echo "  qo'shildi (mavjud LOG_SOURCES/volumes qismi tegilmadi)"
fi

echo "[3/3] Qo'llash"
docker compose up -d

echo
echo "Tayyor. Tekshirish uchun:"
echo "  docker stats --no-stream"
echo "  docker inspect \$(docker compose ps -q postgres) --format 'CpuShares={{.HostConfig.CpuShares}} Mem={{.HostConfig.Memory}}'"
