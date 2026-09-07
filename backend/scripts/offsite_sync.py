#!/usr/bin/env python3
"""Copy the local database backups + raw-event archives to off-site storage.

Everything under "Database backups" and "Archiving raw event detail" in
README.md writes to the *same disk as the live database* by default -- a
dedicated Docker volume (`db_backup_data`) or a local directory. That
protects against a dropped table or a bad migration; it does nothing if
the disk / VM / host itself is lost (hardware failure, a deleted cloud
instance, ransomware, a datacentre fire). This script closes that gap:
it pushes both the pg_dump/sqlite backup files and the gzipped raw-event
archives to a restic repository on storage that is *not* this host --
another server over SFTP, an S3-compatible bucket, an rclone remote, a
restic REST server.

restic (rather than a plain `rsync`) because:
  - the repository is encrypted end-to-end, so an S3 bucket or a rented
    box holding it never sees plaintext -- the pg_dump files themselves
    aren't encrypted at rest the way ARCHIVE_ENCRYPTION_KEY can make the
    archives, and off-site is exactly where that gap matters;
  - content-defined chunking + dedup means a daily multi-GB dump that
    barely changes day to day costs kilobytes per run, not the whole dump;
  - `restic forget --prune` gives a real grandfather-father-son retention
    policy on the off-site copy, independent of the local --keep-days;
  - `restic check` verifies the remote repository is still structurally
    sound without pulling all of it back.

Config comes from the environment (a few also take a CLI flag, which
wins):
  OFFSITE_ENABLED            "false" makes this a no-op that exits 0 -- so
                             a systemd timer can be installed before the
                             destination is decided. Any other value (or
                             unset) runs normally.
  RESTIC_REPOSITORY      /   the restic repo location, e.g.
    OFFSITE_RESTIC_REPOSITORY   sftp:backup@host:/srv/squid-watch-offsite
                             s3:s3.amazonaws.com/my-bucket/squid-watch
                             rclone:remote:squid-watch
  RESTIC_PASSWORD_FILE  /    file holding (or literal value of) the repo's
    RESTIC_PASSWORD            encryption passphrase, with OFFSITE_-prefixed
    OFFSITE_RESTIC_PASSWORD_FILE / OFFSITE_RESTIC_PASSWORD aliases. Store
                             this OFF this host too -- the off-site copy is
                             unrestorable without it, the same warning as
                             ARCHIVE_ENCRYPTION_KEY.
  OFFSITE_PATHS             space-separated paths to back up. Default: the
                             --backup-dir below plus ARCHIVE_OUTPUT_DIR.
                             Non-existent paths are skipped with a warning.
  OFFSITE_KEEP_DAILY / _WEEKLY / _MONTHLY   restic forget policy
                             (default 7 / 8 / 12).
  plus whatever the chosen backend needs -- AWS_ACCESS_KEY_ID /
  AWS_SECRET_ACCESS_KEY, B2_ACCOUNT_ID / B2_ACCOUNT_KEY, an RCLONE_CONFIG
  path, etc. restic reads those straight from the environment; this script
  just doesn't strip them.

Needs the `restic` binary on PATH (`apt install restic`, `apk add
restic`, or https://restic.readthedocs.io) -- not a Python dependency
this project otherwise has. For the Docker deployment use the dedicated
db-offsite service in docker-compose.yml instead (restic/restic image) --
the same relationship db-backup has to backup_database.py.

Intended to run daily, just after the backup timer, plus `--check`
weekly to confirm the remote repo is still restorable (see
deploy/systemd/squid-dashboard-offsite{,-check}.{service,timer}):
    30 4 * * *  cd /path/to/backend && .venv/bin/python scripts/offsite_sync.py \
        --backup-dir /var/backups/squid-watch
"""

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.services.ops_alerting import notify_operator_failure  # noqa: E402

logger = logging.getLogger(__name__)

# Same tag on every snapshot this project makes, so `restic forget` below
# only ever prunes snapshots it created -- a repo an operator also points
# at something else stays safe.
SNAPSHOT_TAG = "squid-watch"


def is_disabled() -> bool:
    return os.environ.get("OFFSITE_ENABLED", "").strip().lower() == "false"


def restic_env() -> dict[str, str]:
    """os.environ plus the OFFSITE_-prefixed aliases mapped onto the bare
    names restic itself reads, so an operator can keep every off-site
    setting under one prefix in .env without also duplicating them."""
    env = os.environ.copy()

    repo = env.get("RESTIC_REPOSITORY") or env.get("OFFSITE_RESTIC_REPOSITORY")
    if not repo:
        raise ValueError(
            "No restic repository configured -- set RESTIC_REPOSITORY (or "
            "OFFSITE_RESTIC_REPOSITORY), or set OFFSITE_ENABLED=false to turn "
            "off-site sync off entirely."
        )
    env["RESTIC_REPOSITORY"] = repo

    if not env.get("RESTIC_PASSWORD_FILE") and not env.get("RESTIC_PASSWORD"):
        alias_file = env.get("OFFSITE_RESTIC_PASSWORD_FILE")
        alias_value = env.get("OFFSITE_RESTIC_PASSWORD")
        if alias_file:
            env["RESTIC_PASSWORD_FILE"] = alias_file
        elif alias_value:
            env["RESTIC_PASSWORD"] = alias_value
        else:
            raise ValueError(
                "No restic repository password -- set RESTIC_PASSWORD_FILE "
                "(preferred) or RESTIC_PASSWORD, or their OFFSITE_ aliases. "
                "Keep a copy of it off this host; the off-site copy is "
                "unrestorable without it."
            )
    return env


def _run_restic(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["restic", *args], check=True, capture_output=True, text=True, env=env)


def ensure_initialised(env: dict[str, str]) -> None:
    """`restic cat config` succeeds iff the repo exists *and* the password
    is right -- only try to create it when that fails, and if `restic init`
    also fails, surface that rather than the (possibly misleading) original
    error: a wrong password looks the same as an absent repo here."""
    probe = subprocess.run(["restic", "cat", "config"], capture_output=True, text=True, env=env)
    if probe.returncode == 0:
        return

    init = subprocess.run(["restic", "init"], capture_output=True, text=True, env=env)
    if init.returncode != 0:
        logger.error(
            "restic repository not usable and init failed",
            extra={
                "cat_config_stderr": probe.stderr.strip(),
                "init_stderr": init.stderr.strip(),
            },
        )
        raise subprocess.CalledProcessError(init.returncode, ["restic", "init"], init.stdout, init.stderr)
    logger.info("Initialised a new restic repository")


def resolve_paths(backup_dir: Path) -> list[Path]:
    raw = os.environ.get("OFFSITE_PATHS")
    if raw:
        candidates = [Path(p) for p in raw.split()]
    else:
        settings = get_settings()
        candidates = [backup_dir, Path(settings.ARCHIVE_OUTPUT_DIR)]

    existing = []
    for path in candidates:
        if path.exists():
            existing.append(path)
        else:
            logger.warning("Skipping off-site path that does not exist", extra={"path": str(path)})
    return existing


def sync(backup_dir: Path, keep_daily: int, keep_weekly: int, keep_monthly: int) -> None:
    if shutil.which("restic") is None:
        raise RuntimeError("restic not found on PATH -- see this script's docstring for how to install it.")
    env = restic_env()
    paths = resolve_paths(backup_dir)
    if not paths:
        raise RuntimeError("No existing paths to back up off-site -- nothing to do.")

    ensure_initialised(env)

    _run_restic(["backup", "--tag", SNAPSHOT_TAG, *[str(p) for p in paths]], env)
    logger.info("Off-site backup complete", extra={"paths": [str(p) for p in paths]})

    _run_restic(
        [
            "forget",
            "--prune",
            "--tag",
            SNAPSHOT_TAG,
            "--keep-daily",
            str(keep_daily),
            "--keep-weekly",
            str(keep_weekly),
            "--keep-monthly",
            str(keep_monthly),
        ],
        env,
    )
    logger.info(
        "Off-site retention applied",
        extra={
            "keep_daily": keep_daily,
            "keep_weekly": keep_weekly,
            "keep_monthly": keep_monthly,
        },
    )


def check() -> None:
    if shutil.which("restic") is None:
        raise RuntimeError("restic not found on PATH -- see this script's docstring for how to install it.")
    _run_restic(["check"], restic_env())
    logger.info("Off-site repository check passed")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Local directory backup_database.py writes to (default ./backups)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the remote repository (restic check) instead of syncing to it",
    )
    parser.add_argument("--keep-daily", type=int, default=_env_int("OFFSITE_KEEP_DAILY", 7))
    parser.add_argument("--keep-weekly", type=int, default=_env_int("OFFSITE_KEEP_WEEKLY", 8))
    parser.add_argument("--keep-monthly", type=int, default=_env_int("OFFSITE_KEEP_MONTHLY", 12))
    args = parser.parse_args()

    configure_logging()

    if is_disabled():
        logger.info("OFFSITE_ENABLED=false -- skipping off-site sync")
        return

    source = "offsite-check" if args.check else "offsite"
    action = "check" if args.check else "sync"
    try:
        if args.check:
            check()
        else:
            sync(args.backup_dir, args.keep_daily, args.keep_weekly, args.keep_monthly)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "restic command failed",
            extra={"returncode": exc.returncode, "stderr": (exc.stderr or "").strip()},
        )
        asyncio.run(
            notify_operator_failure(source, f"Off-site {action} failed (restic exit code {exc.returncode})")
        )
        raise SystemExit(1) from exc
    except (ValueError, RuntimeError) as exc:
        logger.error("Off-site %s could not run", action, extra={"error": str(exc)})
        asyncio.run(notify_operator_failure(source, f"Off-site {action} could not run: {exc}"))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
