#!/usr/bin/env python3
"""Full database backup -- distinct from scripts/archive_weekly_export.py,
which only ever covers one table (raw_events) and is explicitly not a
substitute for this. If the database is lost or corrupted, this is what
stands between that and losing every user, alert setting, aggregate, and
audit-log entry permanently, not just recent event detail.

Branches on DATABASE_URL's scheme (same convention app/core/config.py's own
driver selection already documents) rather than assuming Postgres, since
this also has to work for a SQLite bare-metal install:
- Postgres: `pg_dump --format=custom` (compressed, supports selective
  `pg_restore` later -- not a plain .sql dump).
- SQLite: the *online* backup command (`sqlite3 <path> ".backup ..."`), not
  a raw file copy -- a copy taken while a WAL write is in flight can be
  inconsistent; `.backup` is safe against a live, concurrently-written
  database the same way VACUUM INTO or the C backup API are.

Requires `pg_dump` (matching the target server's major version) or `sqlite3`
on PATH, whichever DATABASE_URL's scheme calls for -- neither is a Python
dependency this project otherwise needs, so neither is installed by default;
see README.md's "Database backups" section for what to install where.

Intended to run daily via cron/systemd timer (see
deploy/systemd/squid-dashboard-backup.service + .timer) or, for the Docker
deployment, see the dedicated db-backup service in docker-compose.yml
instead (a tiny postgres:16-alpine-based script, not this one -- guarantees
an exact pg_dump/server version match without needing Postgres client tools
installed into the Python backend image; this script is still available
there too for an ad-hoc on-demand run via `docker compose exec backend
python scripts/backup_database.py`):
    0 4 * * *  cd /path/to/backend && .venv/bin/python scripts/backup_database.py \
        --output-dir /var/backups/squid-watch
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.services.ops_alerting import notify_operator_failure  # noqa: E402

logger = logging.getLogger(__name__)

BACKUP_FILENAME_PREFIX = "squid-dashboard-backup-"
BACKUP_FILENAME_GLOB = f"{BACKUP_FILENAME_PREFIX}*"


def _prune_old_backups(output_dir: Path, keep_days: int) -> None:
    cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
    for path in output_dir.glob(BACKUP_FILENAME_GLOB):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            logger.info("Purged old backup", extra={"path": str(path)})


def _backup_postgres(database_url: str, dest: Path) -> None:
    # Passing the password as part of a postgresql://user:pass@host/db URI
    # in argv would put it in plain view of any local user via `ps aux` /
    # `/proc/<pid>/cmdline` for the run's duration. Pass the individual
    # connection parts as separate flags instead and hand the password to
    # libpq the way backup_postgres_docker.sh already does -- via the
    # PGPASSWORD environment variable, which isn't visible in argv.
    parsed = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)

    args = ["pg_dump", "--format=custom", f"--file={dest}"]
    if parsed.hostname:
        args += ["--host", parsed.hostname]
    if parsed.port:
        args += ["--port", str(parsed.port)]
    if parsed.username:
        args += ["--username", unquote(parsed.username)]
    args.append(f"--dbname={parsed.path.lstrip('/')}")

    subprocess.run(args, check=True, capture_output=True, text=True, env=env)


def _sqlite_db_path(database_url: str) -> Path:
    parsed = urlsplit(database_url)
    if parsed.netloc:
        raise ValueError(f"Unsupported sqlite DATABASE_URL (unexpected host part): {database_url}")
    # Stripping exactly one leading slash from the parsed path is correct
    # for both forms SQLAlchemy accepts: "sqlite+aiosqlite:///relative/path"
    # (urlsplit hands back path="/relative/path" -- one slash to strip to
    # get the real relative path) and "sqlite+aiosqlite:////absolute/path"
    # (path="//absolute/path" -- stripping one slash still leaves a leading
    # "/", i.e. still absolute).
    path = Path(parsed.path[1:])
    return path if path.is_absolute() else Path.cwd() / path


def _backup_sqlite(database_url: str, dest: Path) -> None:
    db_path = _sqlite_db_path(database_url)
    subprocess.run(
        ["sqlite3", str(db_path), f".backup '{dest}'"],
        check=True,
        capture_output=True,
        text=True,
    )


def run(output_dir: Path, keep_days: int) -> None:
    settings = get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if settings.DATABASE_URL.startswith("postgresql"):
        dest = output_dir / f"{BACKUP_FILENAME_PREFIX}{timestamp}.dump"
        backup_fn = _backup_postgres
    elif settings.DATABASE_URL.startswith("sqlite"):
        dest = output_dir / f"{BACKUP_FILENAME_PREFIX}{timestamp}.db"
        backup_fn = _backup_sqlite
    else:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {settings.DATABASE_URL}")

    try:
        backup_fn(settings.DATABASE_URL, dest)
    except subprocess.CalledProcessError:
        # pg_dump/sqlite3 can still have written a partial file before
        # failing -- leaving it under the normal naming convention would
        # make it indistinguishable from a real, restorable backup until
        # someone actually tries to restore from it.
        dest.unlink(missing_ok=True)
        raise

    logger.info(
        "Database backup complete", extra={"path": str(dest), "size_bytes": dest.stat().st_size}
    )
    _prune_old_backups(output_dir, keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=Path("backups"))
    parser.add_argument(
        "--keep-days", type=int, default=30, help="Delete backup files older than this (default 30)"
    )
    args = parser.parse_args()

    configure_logging()

    try:
        run(args.output_dir, args.keep_days)
    except subprocess.CalledProcessError as exc:
        logger.error("Backup command failed", extra={"returncode": exc.returncode, "stderr": exc.stderr})
        asyncio.run(
            notify_operator_failure(
                "backup", f"Database backup command failed (exit code {exc.returncode})"
            )
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
