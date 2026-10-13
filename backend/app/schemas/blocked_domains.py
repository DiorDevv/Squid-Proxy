from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# denied = a real block (everything blocked except a 407); auth = 407, the
# proxy asking for a login; all = both.
BlockKind = Literal["denied", "auth", "all"]
BlockedDomainSort = Literal["requests", "last", "domain"]


class BlockedDomainRow(BaseModel):
    domain: str
    denied_count: int
    auth_count: int
    # Distinct client IPs with at least one event of the selected kind.
    client_count: int
    branches: list[str]
    # Only LogSource.proxy labels; sources without one are not listed.
    proxies: list[str]
    # Hour buckets (start of the hour, UTC) -- the aggregate's granularity.
    first_seen: datetime
    last_seen: datetime


class BlockedDomainsResponse(BaseModel):
    items: list[BlockedDomainRow]
    total: int
    limit: int
    offset: int
    denied_total: int
    auth_total: int
    # Proxy labels seen in the range, for the proxy filter.
    available_proxies: list[str]
