import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class AnomalySeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyEvent(Base):
    """A detected anomaly, persisted so /api/insights/recent has a durable
    history instead of only ever showing whatever the last aggregator flush
    found. Written by app/services/insights_service.py, populated by
    whichever app/insights/*.py provider is configured (see
    app/insights/__init__.py:get_insights_provider)."""

    __tablename__ = "anomaly_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[AnomalySeverity] = mapped_column(Enum(AnomalySeverity), index=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    # Machine-readable discriminator (e.g. "traffic_spike") + interpolation
    # values for that kind's i18n template -- see app/insights/base.py's
    # Anomaly.kind/params. NULL on rows written before this existed; the
    # frontend falls back to the English title/description above for those.
    kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
