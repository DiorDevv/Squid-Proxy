"""Inert InsightsProvider -- the default until INSIGHTS_PROVIDER opts into
a real one (see app/insights/anomaly.py, app/insights/__init__.py)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, Insight, InsightsProvider
from app.services.log_parser import ParsedEvent


class NoOpInsightsProvider(InsightsProvider):
    async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
        return []

    async def detect_anomalies(self, events: list[ParsedEvent], session: AsyncSession) -> list[Anomaly]:
        return []
