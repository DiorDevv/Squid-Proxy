from datetime import datetime

from pydantic import BaseModel

from app.models.domain_category import DomainCategoryLabel


class AlertSettingsOut(BaseModel):
    branch: str
    sensitive_categories: list[DomainCategoryLabel]
    non_work_minutes_threshold: int
    client_daily_byte_quota_bytes: int | None
    uncategorized_domain_request_threshold: int | None
    updated_at: datetime


class UpdateAlertSettingsRequest(BaseModel):
    sensitive_categories: list[DomainCategoryLabel]
    non_work_minutes_threshold: int
    client_daily_byte_quota_bytes: int | None = None
    uncategorized_domain_request_threshold: int | None = None
