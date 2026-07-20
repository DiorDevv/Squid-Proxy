from datetime import datetime

from pydantic import BaseModel

from app.models.domain_category import DomainCategoryLabel


class ClientSummary(BaseModel):
    client_ip: str
    user: str | None
    total_requests: int
    blocked_requests: int
    total_bytes: int
    last_activity: datetime | None


class DomainTimeSpent(BaseModel):
    domain: str
    total_seconds: int
    session_count: int


class TimeSpentResponse(BaseModel):
    items: list[DomainTimeSpent]


class CategoryTimeSpent(BaseModel):
    category: DomainCategoryLabel
    total_seconds: int
    session_count: int


class CategoryTimeSpentResponse(BaseModel):
    items: list[CategoryTimeSpent]
