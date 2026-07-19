"""Extension point for the insights / anomaly-detection layer.

`app/services/aggregator.py` calls `detect_anomalies` once per flush, right
after that window's events are durably written -- see
`app/insights/anomaly.py` for the first real implementation
(`StatisticalAnomalyProvider`) and `app/insights/noop.py` for the inert
default. `get_insights_provider` (app/insights/__init__.py) is the single
place a future provider gets swapped in via `INSIGHTS_PROVIDER`.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_event import AnomalySeverity
from app.services.log_parser import ParsedEvent

__all__ = ["Anomaly", "AnomalySeverity", "Insight", "InsightsProvider"]


class Insight(BaseModel):
    title: str
    description: str
    generated_at: datetime


class Anomaly(BaseModel):
    title: str
    description: str
    severity: AnomalySeverity
    client_ip: str | None = None
    domain: str | None = None
    generated_at: datetime


class InsightsProvider(ABC):
    """Interface an insights engine implements."""

    @abstractmethod
    async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
        """Summarize a window of events into human-readable insights."""

    @abstractmethod
    async def detect_anomalies(self, events: list[ParsedEvent], session: AsyncSession) -> list[Anomaly]:
        """Flag unusual client/domain behavior within a window of events.

        `session` is provided because meaningful anomaly detection needs
        historical context (recent traffic baselines, whether a domain has
        been seen before) that a single window of in-memory events can't
        answer on its own.
        """
