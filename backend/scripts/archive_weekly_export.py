#!/usr/bin/env python3
"""Archives the last 7 days of raw event detail as gzip-compressed CSV before
retention.py permanently purges it (RETENTION_DAYS_RAW_EVENTS, default 7).

Delegates the actual row streaming to export_service.stream_csv (also used
by GET /api/export) rather than re-querying RawEvent itself, so the two
places that need "every row in a range, batched, no memory blowup" can't
quietly drift apart. This is the same reason that function -- not
export_as_csv's EXPORT_ROW_LIMIT-capped, in-memory-string sibling -- exists:
a week of raw events at the traffic volumes in the brief (1-3M req/day) is
millions of rows, and both this script and the interactive download need
the complete range, not the most recent 100k.

Intended to run weekly via cron/systemd timer, before that data ages out:
    0 3 * * 0  cd /path/to/backend && .venv/bin/python scripts/archive_weekly_export.py

One file per configured branch (report_scheduler.py sends reports the same
way), named squid-events-<branch>-<since_date>_<until_date>.csv.gz in
--output-dir. Archive files older than --keep-days are deleted after a
successful run -- rotation for the *archive* on this server, independent of
the live database's own retention window.

Each successful per-branch write also upserts an ArchiveRun row
(branch -> archived up to `now`), which retention.py checks before its next
purge -- so if this script stops running (cron misconfigured, disk full,
etc.), the next purge notices that branch was never (or not recently
enough) archived and warns instead of silently deleting it anyway.

The per-branch range starts at the *earlier* of "7 days ago" and "where the
last successful run for that branch left off" (ArchiveRun.archived_until),
not always a flat 7 days back. Otherwise a missed run -- the exact failure
this exists to catch -- would recover with one archive covering only the
most recent 7 days, silently skipping the gap between that and the older
data already covered by the previous run; retention.py only sees a single
archived_until marker, so that marker must never claim more coverage than
was actually written.
"""

import argparse
import asyncio
import gzip
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.models.archive_run import ArchiveRun  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402
from app.services.export_service import stream_csv  # noqa: E402

ARCHIVE_FILENAME_GLOB = "squid-events-*.csv.gz"


def _purge_old_archives(output_dir: Path, keep_days: int) -> None:
    cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
    for path in output_dir.glob(ARCHIVE_FILENAME_GLOB):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            print(f"Purged old archive: {path}")


async def archive(output_dir: Path, keep_days: int) -> None:
    await init_db()
    settings = get_settings()
    now = datetime.now(UTC)
    default_since = now - timedelta(days=7)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        for source in settings.effective_log_sources:
            existing_run = await session.get(ArchiveRun, source.branch)
            since = min(default_since, existing_run.archived_until) if existing_run else default_since

            filename = f"squid-events-{source.branch}-{since.date()}_{now.date()}.csv.gz"
            path = output_dir / filename

            # stream_csv's first chunk is exactly the header row; every
            # chunk after that is one full batch of already-terminated CSV
            # rows, so counting those (and skipping the header chunk) gives
            # an exact row count without re-deriving anything about the
            # query itself.
            row_count = 0
            is_header_chunk = True
            with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
                async for chunk in stream_csv(session, since, now, blocked_only=False, branch=source.branch):
                    f.write(chunk)
                    if is_header_chunk:
                        is_header_chunk = False
                    else:
                        row_count += chunk.count("\r\n")

            print(f"Archived {source.branch}: {row_count:,} rows -> {path} ({path.stat().st_size:,} bytes)")

            if existing_run is not None:
                existing_run.archived_until = now
            else:
                session.add(ArchiveRun(branch=source.branch, archived_until=now))
            await session.commit()

    _purge_old_archives(output_dir, keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=Path("archives"))
    parser.add_argument(
        "--keep-days", type=int, default=365, help="Delete archive files older than this (default 365)"
    )
    args = parser.parse_args()

    asyncio.run(archive(args.output_dir, args.keep_days))


if __name__ == "__main__":
    main()
