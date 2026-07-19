"""Config-driven InsightsProvider factory -- the single place a real
implementation is selected (INSIGHTS_PROVIDER=noop|statistical)."""

from functools import lru_cache

from app.core.config import get_settings
from app.insights.anomaly import StatisticalAnomalyProvider
from app.insights.base import InsightsProvider
from app.insights.noop import NoOpInsightsProvider


@lru_cache
def get_insights_provider() -> InsightsProvider:
    provider = get_settings().INSIGHTS_PROVIDER
    if provider == "noop":
        return NoOpInsightsProvider()
    if provider == "statistical":
        return StatisticalAnomalyProvider()
    raise ValueError(f"Unknown insights provider: {provider!r}")
