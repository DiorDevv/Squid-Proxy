#!/bin/sh
# Runs pending Alembic migrations before the app starts -- create_all() in
# app/models/db.py's init_db() only ever creates tables that don't exist
# yet, it never alters existing ones, so without this every schema change
# after a table's first deploy would need a manual ALTER TABLE. Conditioned
# on the uvicorn command specifically so other commands built from this same
# image (e.g. docker-compose.yml's demo-log-generator service, which has no
# DB dependency at all) don't suddenly require database connectivity they
# never needed before.
set -e

if [ "$1" = "uvicorn" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
