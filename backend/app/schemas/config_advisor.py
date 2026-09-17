"""Response model for GET /api/analytics/config-advisor.

Each finding has a machine-readable `code` -- the frontend maps it to a
localized title/explanation -- plus the measured number that tripped it and
a severity. A healthy deployment gets an empty `findings` list.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ConfigFindingCode = Literal[
    "no_caching",
    "no_proxy_auth",
    "no_denies",
    "sensitive_allowed",
    "single_domain_dominant",
]


class ConfigFinding(BaseModel):
    code: ConfigFindingCode
    severity: Literal["info", "warning"]
    # The measured value that tripped this check (a ratio 0..1, a count, or
    # a percentage) -- the frontend formats it per code.
    value: float
    # Optional free-text detail (e.g. the dominant domain's name).
    detail: str | None = None


class ConfigAdvisorResponse(BaseModel):
    checked_at: datetime
    # The window the checks ran over (fixed 24h, not the UI range).
    window_hours: int
    total_requests: int
    findings: list[ConfigFinding]
