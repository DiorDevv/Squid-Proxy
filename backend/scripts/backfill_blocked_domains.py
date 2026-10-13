#!/usr/bin/env python3
"""Fill the blocked-domain hourly aggregates (app/models/blocked_domain_aggregate.py)
from raw_events -- for the history before they existed, or to repair a range.

Postgres only. Run inside the backend container:

    docker compose exec -e PYTHONPATH=/app backend python scripts/backfill_blocked_domains.py --days 7

Each closed hour in the range is recomputed from raw_events and *replaces*
whatever the aggregator wrote for it, so re-running is safe and an hour the
aggregator only half-covered (the deploy hour) comes out exact -- run
`--hours 2` once the deploy hour has ended. The current, still-open hour is
never touched. One day per transaction, one raw_events scan per day: the
per-client rows go to a temp table first and both aggregates are filled
from it.
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.models.db import AsyncSessionLocal  # noqa: E402

_SCAN_SQL = r"""
CREATE TEMP TABLE bd_scan ON COMMIT DROP AS
SELECT date_trunc('hour', "timestamp") AS bucket_ts, branch, coalesce(proxy, '') AS proxy, domain,
       client_ip, coalesce("user", '') AS "user",
       count(*) FILTER (WHERE status_code <> 407) AS denied_count,
       count(*) FILTER (WHERE status_code = 407) AS auth_count
FROM raw_events
WHERE blocked AND domain IS NOT NULL AND domain <> ''
  AND "timestamp" >= :start AND "timestamp" < :end
GROUP BY 1, 2, 3, 4, 5, 6
"""

# Same /24 rule as block_filters.subnet_of.
_CLIENT_SQL = r"""
INSERT INTO blocked_domain_client_hourly_aggregates
    (bucket_ts, branch, proxy, domain, client_ip, "user", subnet, denied_count, auth_count)
SELECT bucket_ts, branch, proxy, domain, client_ip, "user",
       CASE WHEN client_ip ~ '^\d+\.\d+\.\d+\.\d+$'
            THEN regexp_replace(client_ip, '\.\d+$', '.0/24') ELSE client_ip END,
       denied_count, auth_count
FROM bd_scan
ON CONFLICT (bucket_ts, branch, proxy, domain, client_ip, "user")
DO UPDATE SET denied_count = EXCLUDED.denied_count, auth_count = EXCLUDED.auth_count
"""

_DOMAIN_SQL = """
INSERT INTO blocked_domain_hourly_aggregates
    (bucket_ts, branch, proxy, domain, denied_count, auth_count)
SELECT bucket_ts, branch, proxy, domain, sum(denied_count), sum(auth_count)
FROM bd_scan
GROUP BY 1, 2, 3, 4
ON CONFLICT (bucket_ts, branch, proxy, domain)
DO UPDATE SET denied_count = EXCLUDED.denied_count, auth_count = EXCLUDED.auth_count
"""


async def backfill(start: datetime, end: datetime) -> None:
    day_start = start
    while day_start < end:
        day_end = min(day_start + timedelta(days=1), end)
        began = time.monotonic()
        async with AsyncSessionLocal() as session:
            # Hour buckets are UTC hours, as the aggregator writes them.
            await session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            # Parallel workers need /dev/shm, which the postgres container
            # keeps at Docker's 64MB default -- big GROUP BYs fail there.
            await session.execute(text("SET LOCAL max_parallel_workers_per_gather = 0"))
            await session.execute(text("SET LOCAL work_mem = '128MB'"))
            await session.execute(text(_SCAN_SQL), {"start": day_start, "end": day_end})
            clients = (await session.execute(text(_CLIENT_SQL))).rowcount
            domains = (await session.execute(text(_DOMAIN_SQL))).rowcount
            await session.commit()
        print(
            f"{day_start:%Y-%m-%d %H:%M} .. {day_end:%Y-%m-%d %H:%M} UTC: "
            f"{domains} domain rows, {clients} client rows ({time.monotonic() - began:.0f}s)",
            flush=True,
        )
        day_start = day_end


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=7, help="how many days back from the last closed hour")
    parser.add_argument("--hours", type=int, help="hours back instead of --days (e.g. 2 for the deploy hour)")
    args = parser.parse_args()
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - (timedelta(hours=args.hours) if args.hours else timedelta(days=args.days))
    print(f"Backfilling blocked-domain aggregates {start:%Y-%m-%d %H:%M} .. {end:%Y-%m-%d %H:%M} UTC")
    asyncio.run(backfill(start, end))


if __name__ == "__main__":
    main()
