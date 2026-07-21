import enum
from datetime import UTC, datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class DomainCategoryLabel(str, enum.Enum):
    UNCATEGORIZED = "uncategorized"
    SOCIAL_MEDIA = "social_media"
    VIDEO_STREAMING = "video_streaming"
    MUSIC_STREAMING = "music_streaming"
    GAMING = "gaming"
    WORK_TOOLS = "work_tools"
    SHOPPING = "shopping"
    NEWS = "news"
    GAMBLING = "gambling"
    ADULT_CONTENT = "adult_content"
    OTHER = "other"


class DomainCategory(Base):
    """Admin-assigned category for a domain seen in traffic (see
    app/services/domain_category_service.py). A fixed enum rather than free
    text, so filtering/reporting stays consistent instead of fragmenting
    into near-duplicate labels ("social", "Social", "social-media")."""

    __tablename__ = "domain_categories"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[DomainCategoryLabel] = mapped_column(
        Enum(DomainCategoryLabel), default=DomainCategoryLabel.UNCATEGORIZED, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
