from datetime import datetime

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class ReportScheduleState(Base):
    """Tracks when the last scheduled report was sent (see
    app/services/report_scheduler.py). A single row (id=1), persisted in
    the database rather than kept in memory, so a backend restart can't
    cause a duplicate send (state lost, job thinks none was ever sent) or
    a missed one (state lost right after a send, job thinks it's overdue).
    """

    __tablename__ = "report_schedule_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, default=None)
