#!/usr/bin/env python3
"""One-off maintenance: relabel every row tagged with one branch to another,
across every table that has a `branch` column -- for when an operator
renames a branch in LOG_SOURCES (see docker-compose.override.yml) and wants
the *history* to follow, not just new data going forward.

Run from the backend/ dir (or via `docker compose exec backend python
scripts/rename_branch.py ...` for the Docker deployment):

    python scripts/rename_branch.py --from filiallar --to server --dry-run
    python scripts/rename_branch.py --from filiallar --to server

Always run --dry-run first, and take a database backup
(scripts/backup_database.py) before the real run -- this writes directly to
every affected table.

Some tables key a uniqueness constraint on `branch` (alert_settings and
archive_runs use `branch` as their whole primary key; several aggregate
tables include it in a composite unique index) -- if a row already exists
under the *target* branch with the same other key fields (e.g. an
alert_settings row was already saved for "server" before this ran), moving
the "filiallar" row on top of it would violate that constraint. Each
table's update runs in its own SAVEPOINT so a collision there is reported
and skipped rather than aborting every other table's rename; the colliding
source rows are left exactly as they were; see the printed summary for what
needs a manual look afterward.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.models.db import AsyncSessionLocal, init_db  # noqa: E402

# (table, human label) -- every table with a `branch` column as of this
# writing (see app/models/*.py). Order doesn't matter: each runs in its own
# savepoint, independent of the others.
_TABLES = [
    ("raw_events", "Raw events"),
    ("minute_aggregates", "Minute aggregates"),
    ("client_minute_aggregates", "Client minute aggregates"),
    ("client_hourly_aggregates", "Client hourly aggregates"),
    ("client_category_minute_aggregates", "Client category minute aggregates"),
    ("domain_minute_aggregates", "Domain minute aggregates"),
    ("alert_settings", "Alert settings"),
    ("archive_runs", "Archive runs"),
    ("anomaly_events", "Anomaly events"),
    ("export_jobs", "Export jobs"),
    ("audit_log_entries", "Audit log entries"),
    ("users", "User accounts"),
]


async def rename_branch(from_branch: str, to_branch: str, dry_run: bool) -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        print(f"{'[DRY RUN] ' if dry_run else ''}Renaming branch {from_branch!r} -> {to_branch!r}\n")
        conflicts: list[str] = []

        for table, label in _TABLES:
            count = (
                await session.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE branch = :from_branch"),  # noqa: S608
                    {"from_branch": from_branch},
                )
            ).scalar_one()
            if count == 0:
                print(f"  {label:<32} 0 rows (nothing to do)")
                continue

            if dry_run:
                print(f"  {label:<32} {count} row(s) would be renamed")
                continue

            # Each table's UPDATE gets its own savepoint (begin_nested) so a
            # unique-constraint collision here rolls back only this table's
            # attempt -- the other tables' renames (already committed to
            # this outer, not-yet-committed transaction) are unaffected.
            try:
                async with session.begin_nested():
                    result = await session.execute(
                        text(f"UPDATE {table} SET branch = :to_branch WHERE branch = :from_branch"),  # noqa: S608
                        {"to_branch": to_branch, "from_branch": from_branch},
                    )
                print(f"  {label:<32} {result.rowcount} row(s) renamed")
            except IntegrityError as exc:
                conflicts.append(label)
                print(f"  {label:<32} CONFLICT -- left as {from_branch!r} ({exc.orig})")

        if dry_run:
            print("\nDry run only -- nothing was written. Re-run without --dry-run to apply.")
            return

        await session.commit()
        print("\nDone.")
        if conflicts:
            print(
                "\nThe following tables had at least one row that couldn't be renamed "
                f"(a {to_branch!r} row already exists with the same key) and were left as "
                f"{from_branch!r} -- review these manually:\n  - " + "\n  - ".join(conflicts)
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="from_branch", required=True, help="Existing branch tag to rename.")
    parser.add_argument("--to", dest="to_branch", required=True, help="New branch tag.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Only count affected rows per table; write nothing."
    )
    args = parser.parse_args()

    if args.from_branch == args.to_branch:
        parser.error("--from and --to must be different.")

    asyncio.run(rename_branch(args.from_branch, args.to_branch, args.dry_run))


if __name__ == "__main__":
    main()
