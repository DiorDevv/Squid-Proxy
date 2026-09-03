from datetime import datetime

from pydantic import BaseModel

from app.models.domain_category import DomainCategoryLabel


class DomainStat(BaseModel):
    domain: str
    request_count: int
    blocked_count: int
    total_bytes: int
    # Effective category (admin override, else the auto-inferred guess --
    # see category_inference.effective_category) so a UI showing this domain
    # doesn't need to duplicate the categorization heuristic itself.
    category: DomainCategoryLabel


class DomainStatsResponse(BaseModel):
    items: list[DomainStat]


class DomainCategoryOut(BaseModel):
    domain: str
    category: DomainCategoryLabel
    updated_at: datetime


class SetDomainCategoryRequest(BaseModel):
    category: DomainCategoryLabel


class DomainCategoryImportError(BaseModel):
    row: int
    domain: str | None
    reason: str


class DomainCategoryImportResponse(BaseModel):
    applied: int
    errors: list[DomainCategoryImportError]


class CategoryStat(BaseModel):
    category: DomainCategoryLabel
    request_count: int
    blocked_count: int
    total_bytes: int


class CategoryStatsResponse(BaseModel):
    items: list[CategoryStat]


class DomainSummary(BaseModel):
    domain: str
    total_requests: int
    blocked_requests: int
    total_bytes: int
    distinct_client_count: int
    category: DomainCategoryLabel


class DomainClientStat(BaseModel):
    client_ip: str
    # Which proxy/branch this client's visits to the domain came through.
    # The same client_ip can appear under more than one branch (see
    # domain_service.get_domain_clients), so it's a row-level value here,
    # not a property of the IP.
    branch: str | None
    user: str | None
    visit_count: int
    blocked_count: int
    total_bytes: int
    last_visit: datetime | None
