#!/usr/bin/env python3
"""Fill the blocked-domain hourly aggregates (app/models/blocked_domain_aggregate.py)
from raw_events -- for the history before they existed, or to repair a range.

Postgres only. Run inside the backend container:

    docker compose exec backend python scripts/backfill_blocked_domains.py --days 7

Each closed hour in the range is recomputed from raw_events and *replaces*
whatever the aggregator wrote for it, so re-running is safe and an hour the
aggregator only half-covered (the deploy hour) comes out exact. The current,
still-open hour is never touched -- run this after the deploy hour has
ended. One day per transaction; the per-client table is the slow half
(~1 min per day of traffic at ~4M blocked rows/day).
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

_SELECT = """
    FROM raw_events
    WHERE blocked AND domain IS NOT NULL AND domain <> ''
      AND "timestamp" >= :start AND "timestamp" < :end
"""

_DOMAIN_SQL = f"""
INSERT INTO blocked_domain_hourly_aggregates
    (bucket_ts, branch, proxy, domain, denied_count, auth_count)
SELECT date_trunc('hour', "timestamp"), branch, coalesce(proxy, ''), domain,
       count(*) FILTER (WHERE status_code <> 407), count(*) FILTER (WHERE status_code = 407)
{_SELECT}
GROUP BY 1, 2, 3, 4
ON CONFLICT (bucket_ts, branch, proxy, domain)
DO UPDATE SET denied_count = EXCLUDED.denied_count, auth_count = EXCLUDED.auth_count
"""

_CLIENT_SQL = f"""
INSERT INTO blocked_domain_client_hourly_aggregates
    (bucket_ts, branch, proxy, domain, client_ip, denied_count, auth_count)
SELECT date_trunc('hour', "timestamp"), branch, coalesce(proxy, ''), domain, client_ip,
       count(*) FILTER (WHERE status_code <> 407), count(*) FILTER (WHERE status_code = 407)
{_SELECT}
GROUP BY 1, 2, 3, 4, 5
ON CONFLICT (bucket_ts, branch, proxy, domain, client_ip)
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
            params = {"start": day_start, "end": day_end}
            domains = (await session.execute(text(_DOMAIN_SQL), params)).rowcount
            clients = (await session.execute(text(_CLIENT_SQL), params)).rowcount
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
