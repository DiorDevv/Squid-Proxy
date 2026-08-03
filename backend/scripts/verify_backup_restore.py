#!/usr/bin/env python3
"""Verifies that the most recent database backup (see backup_database.py)
actually restores -- "a backup nobody's tested restoring from isn't a real
backup" (README.md's own words in the "Database backups" section). This is
the automation for that: restores into a throwaway database (Postgres) or a
throwaway copy (SQLite), runs a minimal sanity query, then cleans up --
never touches the real database.

Not meant to run on every backup cycle (restoring a full dump isn't cheap)
-- run weekly via cron/systemd timer, same cadence style as
backup_database.py itself; see deploy/systemd/squid-dashboard-backup-verify.
{service,timer} and README.md's "Database backups" section.

For the Docker deployment, see verify_backup_restore_docker.sh instead (this
script assumes `pg_dump`'s counterpart `pg_restore`/`psql`, or `sqlite3`, are
on PATH -- the same tooling backup_database.py itself already requires).
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
from scripts.backup_database import BACKUP_FILENAME_GLOB, _sqlite_db_path  # noqa: E402

logger = logging.getLogger(__name__)

# A minimal, always-present table to sanity-check the restore actually
# produced a queryable schema -- not just that pg_restore/sqlite3 exited 0.
# `users` exists on every install (the first-boot admin bootstrap creates
# it before anything else can happen), so this can't false-positive on an
# empty-but-otherwise-broken restore.
_SANITY_TABLE = "users"


class BackupVerificationError(Exception):
    """Raised on any restore/sanity-check failure, with a human-readable
    message suitable for both the log line and the operator-alert
    webhook."""


def _find_latest_backup(output_dir: Path) -> Path:
    candidates = sorted(output_dir.glob(BACKUP_FILENAME_GLOB), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise BackupVerificationError(f"No backup files found in {output_dir}")
    return candidates[-1]


def _verify_postgres(database_url: str, backup_file: Path) -> int:
    parsed = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)

    conn_args = []
    if parsed.hostname:
        conn_args += ["--host", parsed.hostname]
    if parsed.port:
        conn_args += ["--port", str(parsed.port)]
    if parsed.username:
        conn_args += ["--username", unquote(parsed.username)]

    # Never the real database -- a fresh, uniquely-named one, dropped in the
    # finally block below regardless of how the restore/sanity-check goes.
    throwaway_db = f"squid_dashboard_restore_verify_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    def _psql(sql: str, dbname: str = "postgres") -> str:
        result = subprocess.run(
            ["psql", *conn_args, "--dbname", dbname, "--tuples-only", "--command", sql],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.stdout.strip()

    _psql(f'CREATE DATABASE "{throwaway_db}"')
    try:
        subprocess.run(
            ["pg_restore", *conn_args, "--dbname", throwaway_db, "--no-owner", str(backup_file)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        row_count = _psql(f"SELECT count(*) FROM {_SANITY_TABLE}", dbname=throwaway_db)
        return int(row_count)
    except subprocess.CalledProcessError as exc:
        raise BackupVerificationError(
            f"pg_restore/sanity-check failed for {backup_file.name}: {exc.stderr}"
        ) from exc
    finally:
        _psql(f'DROP DATABASE IF EXISTS "{throwaway_db}"')


def _verify_sqlite(backup_file: Path, tmp_path: Path) -> int:
    tmp_path.write_bytes(backup_file.read_bytes())
    try:
        integrity = subprocess.run(
            ["sqlite3", str(tmp_path), "PRAGMA integrity_check;"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if integrity != "ok":
            raise BackupVerificationError(f"Integrity check failed for {backup_file.name}: {integrity}")

        row_count = subprocess.run(
            ["sqlite3", str(tmp_path), f"SELECT count(*) FROM {_SANITY_TABLE};"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return int(row_count)
    except subprocess.CalledProcessError as exc:
        raise BackupVerificationError(
            f"sqlite3 restore/sanity-check failed for {backup_file.name}: {exc.stderr}"
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def run(output_dir: Path, backup_file: Path | None = None) -> None:
    settings = get_settings()
    backup_file = backup_file or _find_latest_backup(output_dir)

    if settings.DATABASE_URL.startswith("postgresql"):
        row_count = _verify_postgres(settings.DATABASE_URL, backup_file)
    elif settings.DATABASE_URL.startswith("sqlite"):
        # Reuses backup_database.py's own path-resolution helper so a
        # relative DATABASE_URL resolves the same way in both scripts --
        # the actual source DB path isn't read here, only used to confirm
        # sqlite is the active dialect; the restore target is always a
        # fresh tmp file, never the real squid_dashboard.db.
        _sqlite_db_path(settings.DATABASE_URL)
        row_count = _verify_sqlite(backup_file, backup_file.with_suffix(".restore_verify_tmp.db"))
    else:
        raise BackupVerificationError(f"Unsupported DATABASE_URL scheme: {settings.DATABASE_URL}")

    logger.info(
        "Backup restore verification succeeded",
        extra={"backup_file": str(backup_file), "sanity_row_count": row_count},
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=Path("backups"))
    parser.add_argument(
        "--backup-file",
        type=Path,
        default=None,
        help="Verify this specific file instead of the newest one in --output-dir.",
    )
    args = parser.parse_args()

    configure_logging()

    try:
        run(args.output_dir, args.backup_file)
    except BackupVerificationError as exc:
        logger.error("Backup restore verification failed", extra={"error": str(exc)})
        asyncio.run(notify_operator_failure("backup_restore_verify", str(exc)))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
