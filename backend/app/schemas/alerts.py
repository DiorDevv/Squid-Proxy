from datetime import datetime

from pydantic import BaseModel, Field

from app.models.alert_rule import AlertRuleMetric, AlertRuleScope
from app.models.anomaly_event import AnomalySeverity
from app.models.domain_category import DomainCategoryLabel


class AlertSettingsOut(BaseModel):
    branch: str
    sensitive_categories: list[DomainCategoryLabel]
    non_work_minutes_threshold: int
    client_daily_byte_quota_bytes: int | None
    uncategorized_domain_request_threshold: int | None
    telegram_chat_id: str | None
    updated_at: datetime


class UpdateAlertSettingsRequest(BaseModel):
    sensitive_categories: list[DomainCategoryLabel]
    non_work_minutes_threshold: int
    client_daily_byte_quota_bytes: int | None = None
    uncategorized_domain_request_threshold: int | None = None
    telegram_chat_id: str | None = None


class TelegramLinkCodeOut(BaseModel):
    code: str
    expires_at: datetime


class TelegramLinkStatusOut(BaseModel):
    consumed: bool
    expired: bool
    chat_id: str | None


class TelegramSuperAdminOut(BaseModel):
    chat_id: str | None


class AlertRuleOut(BaseModel):
    id: int
    branch: str
    name: str
    scope: AlertRuleScope
    metric: AlertRuleMetric
    window_minutes: int
    threshold: int
    severity: AnomalySeverity
    enabled: bool
    updated_at: datetime


class CreateAlertRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scope: AlertRuleScope
    metric: AlertRuleMetric
    window_minutes: int = Field(ge=1, le=1440)
    threshold: int = Field(gt=0)
    severity: AnomalySeverity = AnomalySeverity.HIGH
    enabled: bool = True


class UpdateAlertRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scope: AlertRuleScope
    metric: AlertRuleMetric
    window_minutes: int = Field(ge=1, le=1440)
    threshold: int = Field(gt=0)
    severity: AnomalySeverity
    enabled: bool
