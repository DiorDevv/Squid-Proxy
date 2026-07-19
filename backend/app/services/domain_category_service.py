"""Admin-assigned domain -> category mapping (see api/routes/domain_categories.py)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_category import DomainCategory, DomainCategoryLabel


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


async def set_category(session: AsyncSession, domain: str, category: DomainCategoryLabel) -> DomainCategory:
    row = (
        await session.execute(select(DomainCategory).where(DomainCategory.domain == domain))
    ).scalar_one_or_none()
    if row is None:
        row = DomainCategory(domain=domain, category=category)
        session.add(row)
    else:
        row.category = category
    await session.commit()
    await session.refresh(row)
    return row
