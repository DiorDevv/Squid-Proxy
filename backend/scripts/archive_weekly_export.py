#!/usr/bin/env python3
"""CLI wrapper around app.services.archive_service.archive -- see that
module's docstring for what archiving actually does and why.

Archiving now also runs automatically in-process (see
app/services/archive_scheduler.py, ARCHIVE_ENABLED in app/core/config.py),
so this script is no longer required for a default setup. It's still useful
for an immediate on-demand run, or if you'd rather manage the schedule
yourself entirely externally (set ARCHIVE_ENABLED=false and use this via
cron/systemd timer instead):
    0 3 * * 0  cd /path/to/backend && .venv/bin/python scripts/archive_weekly_export.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging  # noqa: E402
from app.models.db import init_db  # noqa: E402
from app.services.archive_service import archive  # noqa: E402


async def _run(output_dir: Path, keep_days: int) -> None:
    # Only the standalone path needs this -- the in-process scheduler runs
    # after the app's own lifespan-startup init_db() already did it.
    await init_db()
    await archive(output_dir, keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=Path("archives"))
    parser.add_argument(
        "--keep-days", type=int, default=365, help="Delete archive files older than this (default 365)"
    )
    args = parser.parse_args()

    # archive_service logs (not prints) its results -- fine for the
    # in-process scheduler, which runs under the app's own configure_logging()
    # setup (see main.py's lifespan), but this standalone entry point has no
    # log handler at all otherwise, so a cron/systemd-timer run would
    # silently produce no visible output. Same JSON formatter either way,
    # rather than a second, weaker ad-hoc format just for this path.
    configure_logging()

    asyncio.run(_run(args.output_dir, args.keep_days))


if __name__ == "__main__":
    main()
