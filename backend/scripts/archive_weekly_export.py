#!/usr/bin/env python3
"""Archives the last 7 days of raw event detail as gzip-compressed CSV before
retention.py permanently purges it (RETENTION_DAYS_RAW_EVENTS, default 7).

Streams rows in batches (keyset-paginated by id) straight into a gzip
writer rather than building the export in memory -- a week of raw events at
the traffic volumes in the brief (1-3M req/day) is millions of rows, far
past what fits comfortably as one in-memory string. This deliberately
doesn't reuse export_service.export_as_csv, which caps at EXPORT_ROW_LIMIT
(100k) and holds the whole result in memory -- a sensible limit for an
admin's interactive HTTP download, wrong for a full-week unattended archive.

Intended to run weekly via cron/systemd timer, before that data ages out:
    0 3 * * 0  cd /path/to/backend && .venv/bin/python scripts/archive_weekly_export.py

One file per configured branch (report_scheduler.py sends reports the same
way), named squid-events-<branch>-<since_date>_<until_date>.csv.gz in
--output-dir. Archive files older than --keep-days are deleted after a
successful run -- rotation for the *archive* on this server, independent of
the live database's own retention window.
"""

import argparse
import asyncio
import csv
import gzip
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402
from app.models.raw_event import RawEvent  # noqa: E402
from app.services.export_service import _COLUMNS, _escape_csv_formula, _row_to_dict  # noqa: E402

BATCH_SIZE = 5_000
ARCHIVE_FILENAME_GLOB = "squid-events-*.csv.gz"


async def _stream_branch_csv(
    session: AsyncSession, since: datetime, until: datetime, branch: str, text_file: TextIO
) -> int:
    writer = csv.DictWriter(text_file, fieldnames=_COLUMNS)
    writer.writeheader()

    total = 0
    last_id = 0
    while True:
        query = (
            select(RawEvent)
            .where(
                RawEvent.branch == branch,
                RawEvent.timestamp >= since,
                RawEvent.timestamp < until,
                RawEvent.id > last_id,
            )
            .order_by(RawEvent.id)
            .limit(BATCH_SIZE)
        )
        rows = (await session.execute(query)).scalars().all()
        if not rows:
            break

        for row in rows:
            record = _row_to_dict(row)
            for column in ("client_ip", "user", "url", "domain"):
                record[column] = _escape_csv_formula(record[column])
            writer.writerow(record)

        total += len(rows)
        last_id = rows[-1].id
        if len(rows) < BATCH_SIZE:
            break

    return total


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
    since = now - timedelta(days=7)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        for source in settings.effective_log_sources:
            filename = f"squid-events-{source.branch}-{since.date()}_{now.date()}.csv.gz"
            path = output_dir / filename
            with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
                count = await _stream_branch_csv(session, since, now, source.branch, f)
            print(f"Archived {source.branch}: {count:,} rows -> {path} ({path.stat().st_size:,} bytes)")

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
