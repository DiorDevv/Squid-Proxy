"""Admin-assigned domain -> category mapping (see api/routes/domain_categories.py)."""

import csv
import io
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction
from app.models.domain_category import DomainCategory, DomainCategoryLabel
from app.services import audit_service
from app.services.db_upsert import chunk_rows, declared_table, max_variables_for

CSV_FIELDNAMES = ["domain", "category"]
# Bounds how many rows a single import request will process -- an admin
# bulk-editing their own category assignments is at most a few thousand rows
# in practice; an unbounded file would let one request build an unbounded
# in-memory `entries` dict (see _bulk_upsert_categories) or an unbounded CSV
# read in the first place.
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


# Leading characters a spreadsheet app (Excel, Google Sheets, LibreOffice)
# treats as "this cell is a formula" -- a domain stored via PUT /{domain}
# isn't validated as a real hostname (it's just a dict key), so an admin
# (or anyone able to influence a stored value) could plant one of these and
# have it execute when a *different* admin opens the exported CSV directly
# in a spreadsheet. Prefixing with a single quote is the standard mitigation
# (the spreadsheet renders the cell as literal text); _unescape_csv_formula
# strips it back off on import so the round-trip stays lossless.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _escape_csv_formula(value: str) -> str:
    return f"'{value}" if value.startswith(_CSV_FORMULA_PREFIXES) else value


def _unescape_csv_formula(value: str) -> str:
    if value.startswith("'") and value[1:].startswith(_CSV_FORMULA_PREFIXES):
        return value[1:]
    return value


def export_to_csv(rows: list[DomainCategory]) -> str:
    """Every admin-assigned override as a `domain,category` CSV -- the exact
    shape import_from_csv() expects back, so "export, edit in a
    spreadsheet, re-import" round-trips cleanly."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        writer.writerow({"domain": _escape_csv_formula(row.domain), "category": row.category.value})
    return buffer.getvalue()


async def _bulk_upsert_categories(session: AsyncSession, entries: dict[str, DomainCategoryLabel]) -> None:
    """Upserts many (domain -> category) pairs via one or a few `INSERT ...
    ON CONFLICT DO UPDATE` statements instead of one row-by-row SELECT +
    commit per domain (what import_from_csv used to do via set_category(),
    turning a large import into thousands of sequential round trips inside a
    single HTTP request). `entries` is already deduplicated by domain --
    caller decides which category wins for a domain listed twice in one
    CSV. Batches via chunk_rows the same way Aggregator.flush() batches its
    upserts, staying under the dialect's per-statement bound-parameter
    limit (see db_upsert.py) even for MAX_IMPORT_ROWS-sized imports.
    Does not commit -- caller commits once alongside the audit entry, so
    the whole import applies atomically or not at all."""
    if not entries:
        return
    now = datetime.now(UTC)
    rows = [
        {"domain": domain, "category": category, "updated_at": now} for domain, category in entries.items()
    ]

    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert
    for batch in chunk_rows(rows, columns_per_row=len(rows[0]), max_variables=max_variables_for(session)):
        stmt = insert(declared_table(DomainCategory)).values(list(batch))
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain"],
            set_={"category": stmt.excluded.category, "updated_at": stmt.excluded.updated_at},
        )
        await session.execute(stmt)


async def import_from_csv(
    session: AsyncSession, csv_text: str, actor_user_id: str
) -> tuple[int, list[tuple[int, str | None, str]]]:
    """Bulk-applies `domain,category` rows (see export_to_csv for the
    expected shape). Each row is validated independently -- one bad row
    (missing domain, a category value that isn't one of DomainCategoryLabel's
    fixed set) is skipped and reported, never a reason to abort rows that
    were already fine, matching this project's established per-item-isolation
    pattern (see scripts/rename_branch.py). Valid rows are applied as one
    batched write (_bulk_upsert_categories) plus a single summary audit
    entry, not one DB round trip and one audit row per row -- this used to
    call set_category() per row, which meant up to MAX_IMPORT_ROWS sequential
    commits inside one request (a real timeout risk) and an audit log
    entry-per-row for what's conceptually one admin action.
    Returns (applied_count, errors), where each error is
    (1-indexed data row number, domain-or-None, human-readable reason).
    applied_count counts valid *rows* (matching the CSV the admin uploaded),
    even though a domain repeated across rows only costs one DB write --
    last row for a repeated domain wins."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or set(CSV_FIELDNAMES) - set(reader.fieldnames):
        return 0, [(0, None, f"CSV must have a header row with columns: {', '.join(CSV_FIELDNAMES)}")]

    applied = 0
    entries: dict[str, DomainCategoryLabel] = {}
    errors: list[tuple[int, str | None, str]] = []
    for row_number, row in enumerate(reader, start=1):
        if row_number > MAX_IMPORT_ROWS:
            errors.append((row_number, None, f"Stopped after {MAX_IMPORT_ROWS} rows."))
            break

        domain = _unescape_csv_formula((row.get("domain") or "").strip()).lower()
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

        entries[domain] = category
        applied += 1

    await _bulk_upsert_categories(session, entries)
    if entries:
        preview = ", ".join(list(entries)[:10])
        if len(entries) > 10:
            preview += ", ..."
        await audit_service.record(
            session,
            action=AuditAction.DOMAIN_CATEGORY_IMPORTED,
            actor_user_id=actor_user_id,
            detail=f"{len(entries)} domain(s) via CSV import: {preview}",
        )
    await session.commit()

    return applied, errors
