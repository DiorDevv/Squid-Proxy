#!/usr/bin/env python3
"""One-off maintenance: merge two `archive_runs` rows left over after
rename_branch.py hit a conflict on this table (it's the one table where
`branch` is the sole primary key, so a rename can't just overwrite an
existing row for the target branch -- see rename_branch.py's docstring).

`archive_runs` tracks, per branch, the watermark up to which
scripts/archive_weekly_export.py has archived raw_events; RetentionJob.purge()
uses it to warn before permanently deleting events that were never archived.
Merging two rows for what is now the same physical branch should keep the
*earlier* (more conservative) archived_until -- understating archive progress
only causes an extra warning, while overstating it could let RetentionJob
silently purge data that was never actually archived.

Run from the backend/ dir (or via `docker compose exec backend python
scripts/merge_archive_run.py ...` for the Docker deployment):

    python scripts/merge_archive_run.py --from filiallar --to server

This keeps the row named --to (creating it from --from's value if --to
doesn't exist yet), sets its archived_until to the earlier of the two
timestamps, and deletes the --from row.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.models.archive_run import ArchiveRun  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402


async def merge_archive_run(from_branch: str, to_branch: str) -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        old = (
            await session.execute(select(ArchiveRun).where(ArchiveRun.branch == from_branch))
        ).scalar_one_or_none()
        new = (
            await session.execute(select(ArchiveRun).where(ArchiveRun.branch == to_branch))
        ).scalar_one_or_none()

        print(f"{from_branch!r} archived_until: {old.archived_until if old else None}")
        print(f"{to_branch!r} archived_until: {new.archived_until if new else None}")

        if old is None:
            print(f"\nNo row for {from_branch!r} -- nothing to merge.")
            return

        if new is None:
            new = ArchiveRun(branch=to_branch, archived_until=old.archived_until)
            session.add(new)
            await session.delete(old)
            await session.commit()
            print(
                f"\nNo existing {to_branch!r} row -- renamed in place: "
                f"archived_until = {old.archived_until}"
            )
            return

        safest = min(old.archived_until, new.archived_until)
        new.archived_until = safest
        await session.delete(old)
        await session.commit()
        print(f"\nMerged -> {to_branch!r}.archived_until = {safest}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="from_branch", required=True, help="Branch row to merge away.")
    parser.add_argument("--to", dest="to_branch", required=True, help="Branch row to keep.")
    args = parser.parse_args()

    if args.from_branch == args.to_branch:
        parser.error("--from and --to must be different.")

    asyncio.run(merge_archive_run(args.from_branch, args.to_branch))


if __name__ == "__main__":
    main()
