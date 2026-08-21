"""Admin-assigned domain -> category mapping (see api/routes/domain_categories.py)."""

import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction
from app.models.domain_category import DomainCategory, DomainCategoryLabel
from app.services import audit_service

CSV_FIELDNAMES = ["domain", "category"]
# Bounds how many rows a single import request will process -- an admin
# bulk-editing their own category assignments is at most a few thousand
# rows in practice; an unbounded file would let one request tie up the
# event loop indefinitely (set_category commits once per row) or exhaust
# memory reading it in.
MAX_IMPORT_ROWS = 20_000


async def list_all(session: AsyncSession) -> list[DomainCategory]:
    rows = (await session.execute(select(DomainCategory).order_by(DomainCategory.domain))).scalars().all()
    return list(rows)


async def get_overrides_map(session: AsyncSession) -> dict[str, DomainCategoryLabel]:
    """Every admin-assigned override, keyed by domain -- the input
    category_inference.effective_category() combines with the auto-inferred
    guess. A flat dict rather than a per-domain query, since every caller
    needs this for a whole batch of domains at once (a ranking list, a
    time-spent breakdown), not just one."""
    rows = (await session.execute(select(DomainCategory.domain, DomainCategory.category))).all()
    return {domain: category for domain, category in rows}


async def set_category(
    session: AsyncSession, domain: str, category: DomainCategoryLabel, actor_user_id: str
) -> DomainCategory:
    row = (
        await session.execute(select(DomainCategory).where(DomainCategory.domain == domain))
    ).scalar_one_or_none()
    if row is None:
        row = DomainCategory(domain=domain, category=category)
        session.add(row)
    else:
        row.category = category
    await audit_service.record(
        session,
        action=AuditAction.DOMAIN_CATEGORY_SET,
        actor_user_id=actor_user_id,
        detail=f"domain={domain}, category={category.value}",
    )
    await session.commit()
    await session.refresh(row)
    return row


def export_to_csv(rows: list[DomainCategory]) -> str:
    """Every admin-assigned override as a `domain,category` CSV -- the exact
    shape import_from_csv() expects back, so "export, edit in a
    spreadsheet, re-import" round-trips cleanly."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        writer.writerow({"domain": row.domain, "category": row.category.value})
    return buffer.getvalue()


async def import_from_csv(
    session: AsyncSession, csv_text: str, actor_user_id: str
) -> tuple[int, list[tuple[int, str | None, str]]]:
    """Bulk-applies `domain,category` rows (see export_to_csv for the
    expected shape). Each row is applied independently via set_category --
    one bad row (missing domain, a category value that isn't one of
    DomainCategoryLabel's fixed set) is skipped and reported, never a
    reason to abort rows that were already fine, matching this project's
    established per-item-isolation pattern (see scripts/rename_branch.py).
    Returns (applied_count, errors), where each error is
    (1-indexed data row number, domain-or-None, human-readable reason)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or set(CSV_FIELDNAMES) - set(reader.fieldnames):
        return 0, [(0, None, f"CSV must have a header row with columns: {', '.join(CSV_FIELDNAMES)}")]

    applied = 0
    errors: list[tuple[int, str | None, str]] = []
    for row_number, row in enumerate(reader, start=1):
        if row_number > MAX_IMPORT_ROWS:
            errors.append((row_number, None, f"Stopped after {MAX_IMPORT_ROWS} rows."))
            break

        domain = (row.get("domain") or "").strip().lower()
        category_raw = (row.get("category") or "").strip()
        if not domain:
            errors.append((row_number, None, "Missing domain."))
            continue
        try:
            category = DomainCategoryLabel(category_raw)
        except ValueError:
            valid = ", ".join(label.value for label in DomainCategoryLabel)
            errors.append((row_number, domain, f"Unknown category {category_raw!r}. Valid: {valid}."))
            continue

        await set_category(session, domain, category, actor_user_id)
        applied += 1

    return applied, errors
