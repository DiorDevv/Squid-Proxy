#!/usr/bin/env python3
"""One-off report: every distinct domain seen in raw_events over the last N
days, with a request count, most-frequent first -- written to a file so an
operator can hand the list to someone (or something) doing manual domain
categorization (see app/services/category_inference.py's _KNOWN_HOSTNAMES
and app/services/domain_category_service.py's admin overrides) without
pasting raw log lines (client IPs, full URLs, timestamps) anywhere.

Only domain + count are read -- nothing else from the row.

Run from the backend/ dir (or via `docker compose exec backend python
scripts/domain_traffic_report.py ...` for the Docker deployment):

    python scripts/domain_traffic_report.py --days 2
    python scripts/domain_traffic_report.py --days 2 --branch server
    python scripts/domain_traffic_report.py --days 2 --out domains_2d.txt
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.models.db import AsyncSessionLocal, init_db  # noqa: E402


async def domain_traffic_report(days: int, branch: str | None, out_path: str) -> None:
    await init_db()
    since = datetime.now(UTC) - timedelta(days=days)

    conditions = ["timestamp >= :since", "domain IS NOT NULL"]
    params: dict[str, object] = {"since": since}
    if branch is not None:
        conditions.append("branch = :branch")
        params["branch"] = branch

    query = f"""
        SELECT domain, COUNT(*) AS cnt
        FROM raw_events
        WHERE {" AND ".join(conditions)}
        GROUP BY domain
        ORDER BY cnt DESC
    """  # noqa: S608 -- conditions are fixed strings above, never user input

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(query), params)).all()

    with open(out_path, "w") as f:
        for domain, cnt in rows:
            f.write(f"{cnt}\t{domain}\n")

    print(f"{len(rows)} distinct domain(s) over the last {days} day(s) written to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=2, help="How many days back to look (default: 2).")
    parser.add_argument("--branch", default=None, help="Limit to one branch (default: every branch).")
    parser.add_argument(
        "--out", default="domains_report.txt", help="Output file path (default: domains_report.txt)."
    )
    args = parser.parse_args()

    asyncio.run(domain_traffic_report(args.days, args.branch, args.out))


if __name__ == "__main__":
    main()
