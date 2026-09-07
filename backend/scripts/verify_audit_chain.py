#!/usr/bin/env python3
"""Verify the audit log's tamper-evidence hash chain from outside the app.

Every audit_log_entries row stores entry_hash = SHA-256 over its own
immutable fields plus the previous row's entry_hash (see
app/services/audit_service.compute_entry_hash). Altering, inserting, or
deleting any row breaks the chain from that point on -- this walks the
whole chain and reports the first break, if any.

Same check as GET /api/audit-log/verify, but runnable without the API up
(a cron sanity check, or a compliance reviewer with only DB access):

    cd backend && .venv/bin/python scripts/verify_audit_chain.py

Exits 0 if the chain is intact, 1 if it's broken or can't be read. Reads
DATABASE_URL the same way the app does.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402
from app.services.audit_service import verify_chain  # noqa: E402


async def _run() -> int:
    await init_db()
    async with AsyncSessionLocal() as session:
        result = await verify_chain(session)

    if result.ok:
        print(f"OK: audit log hash chain intact ({result.entries_checked} entries).")
        return 0

    b = result.broken_at or {}
    print("BROKEN: audit log hash chain verification failed.", file=sys.stderr)
    print(f"  first valid entries: {result.entries_checked}", file=sys.stderr)
    print(f"  break at position:   {b.get('position')}", file=sys.stderr)
    print(f"  entry id:            {b.get('id')}", file=sys.stderr)
    print(f"  entry created_at:    {b.get('created_at')}", file=sys.stderr)
    print(f"  reason:              {b.get('reason')}", file=sys.stderr)
    return 1


def main() -> None:
    configure_logging()
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
