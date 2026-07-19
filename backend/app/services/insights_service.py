"""Persists and reads back anomalies detected by the configured
InsightsProvider (see app/insights/__init__.py, app/services/aggregator.py)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly
from app.models.anomaly_event import AnomalyEvent
from app.schemas.common import Page
from app.schemas.insights import AnomalyEventOut


def persist(session: AsyncSession, anomalies: list[Anomaly]) -> list[AnomalyEvent]:
    rows = [
        AnomalyEvent(
            generated_at=anomaly.generated_at,
            title=anomaly.title,
            description=anomaly.description,
            severity=anomaly.severity,
            client_ip=anomaly.client_ip,
            domain=anomaly.domain,
        )
        for anomaly in anomalies
    ]
    session.add_all(rows)
    return rows


async def list_recent(session: AsyncSession, limit: int, offset: int) -> Page[AnomalyEventOut]:
    query = (
        select(AnomalyEvent).order_by(AnomalyEvent.generated_at.desc()).limit(limit).offset(offset)
    )
    rows = (await session.execute(query)).scalars().all()
    total = (await session.execute(select(func.count()).select_from(AnomalyEvent))).scalar_one()

    items = [
        AnomalyEventOut(
            id=row.id,
            generated_at=row.generated_at,
            title=row.title,
            description=row.description,
            severity=row.severity,
            client_ip=row.client_ip,
            domain=row.domain,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
