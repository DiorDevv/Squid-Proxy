import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class SystemEventSeverity(str, enum.Enum):
    WARNING = "warning"
    ERROR = "error"


class SystemEvent(Base):
    """A durable record of an operational failure -- the log tailer dying, a
    background job erroring out, a backup/retention/archiving run failing.

    These already fire OPS_ALERT_WEBHOOK_URL (app/services/ops_alerting.py),
    but that is fire-and-forget: a deployment with no webhook configured
    kept no trace at all. Every notify_operator_failure() call now also
    lands a row here, so Settings -> System health can show "what has
    broken lately" whether or not anyone was watching a webhook. Pruned by
    RetentionJob after RETENTION_DAYS_SYSTEM_EVENTS days.
    """

    __tablename__ = "system_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True, default=lambda: datetime.now(UTC))
    # Short stable tag identifying what broke: "backup", "offsite",
    # "retention", "log_tailer:<branch>", "archiving", ...
    source: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[SystemEventSeverity] = mapped_column(
        Enum(SystemEventSeverity), default=SystemEventSeverity.ERROR, index=True
    )
    message: Mapped[str] = mapped_column(Text)
