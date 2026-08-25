from datetime import UTC, datetime

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class AlertSettings(Base):
    """Admin-tunable thresholds for the category/quota anomaly checks (see
    app/insights/anomaly.py, app/services/category_usage_monitor.py,
    app/services/quota_monitor.py). One row per branch (keyed by `branch`,
    not a surrogate id) rather than a generic key-value settings table --
    there are only ever a handful of these fields and each has its own type;
    see app/services/alert_settings_service.py for how a missing row falls
    back to defaults instead of being created eagerly on every read.
    """

    __tablename__ = "alert_settings"

    branch: Mapped[str] = mapped_column(String(64), primary_key=True, default=DEFAULT_BRANCH)
    # Comma-separated DomainCategoryLabel values (e.g. "gambling,gaming") --
    # not a native array/JSON column, to stay portable across SQLite and
    # Postgres without a dialect-specific type.
    sensitive_categories: Mapped[str] = mapped_column(String(255), default="")
    non_work_minutes_threshold: Mapped[int] = mapped_column(Integer, default=120)
    client_daily_byte_quota_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    # None (not 0) means off -- a domain with 24h request_count >= this
    # gets flagged as "high-traffic but uncategorized" (see
    # app/services/uncategorized_domain_monitor.py).
    uncategorized_domain_request_threshold: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    # Telegram chat/group id that this branch's high-severity anomalies are
    # delivered to, in addition to (not instead of) TELEGRAM_SUPER_ADMIN_CHAT_ID
    # -- see app/services/telegram_alerting.py.
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
