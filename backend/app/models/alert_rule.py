import enum
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.anomaly_event import AnomalySeverity
from app.models.db import Base
from app.models.types import UTCDateTime


class AlertRuleScope(str, enum.Enum):
    CLIENT_IP = "client_ip"
    DOMAIN = "domain"
    BRANCH = "branch"


class AlertRuleMetric(str, enum.Enum):
    REQUEST_COUNT = "request_count"
    BLOCKED_COUNT = "blocked_count"
    TOTAL_BYTES = "total_bytes"
    BYTES_RECEIVED = "bytes_received"


class AlertRule(Base):
    """Admin-defined custom threshold rule: "if <metric>, summed per
    <scope>, exceeds <threshold> within the trailing <window_minutes>,
    raise an anomaly at <severity>." Evaluated every aggregator flush (see
    app/insights/anomaly.py's StatisticalAnomalyProvider._custom_rules)
    against the same per-minute aggregate tables the built-in checks
    already read -- no new data collection needed.

    This is the generic escape hatch for "a new kind of spike-detection
    rule" so it doesn't need a code change/redeploy, only a row here (see
    Settings -> Alerts -> Custom rules); the built-in checks (traffic
    spike, client quota, sensitive category, ...) stay as they are since
    their logic is more than a plain metric/threshold comparison.
    """

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[AlertRuleScope] = mapped_column(Enum(AlertRuleScope))
    metric: Mapped[AlertRuleMetric] = mapped_column(Enum(AlertRuleMetric))
    window_minutes: Mapped[int] = mapped_column(Integer, default=10)
    # Bytes for total_bytes/bytes_received, a plain count for
    # request_count/blocked_count.
    threshold: Mapped[int] = mapped_column(BigInteger)
    severity: Mapped[AnomalySeverity] = mapped_column(Enum(AnomalySeverity), default=AnomalySeverity.HIGH)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
