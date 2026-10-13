from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# denied = a real block (everything blocked except a 407); auth = 407, the
# proxy asking for a login; all = both.
BlockKind = Literal["denied", "auth", "all"]
# What the Analysis view groups the filtered blocks by.
BlockGroupBy = Literal["domain", "client", "user", "subnet", "branch", "proxy"]
BlockGroupSort = Literal["requests", "clients", "users", "domains", "last", "key"]


class BlockGroupRow(BaseModel):
    # The grouped value: a domain, client IP, login ("" = no login), /24
    # subnet, branch or proxy label ("" = source without one).
    key: str
    denied_count: int
    auth_count: int
    # Distinct values with an event of the selected kind inside this group.
    client_count: int
    user_count: int
    domain_count: int
    branches: list[str]
    proxies: list[str]
    # Hour buckets (start of the hour, UTC) -- the aggregate's granularity.
    first_seen: datetime
    last_seen: datetime


class BlockGroupsResponse(BaseModel):
    group: BlockGroupBy
    items: list[BlockGroupRow]
    total: int
    limit: int
    offset: int


class BlockSeriesPoint(BaseModel):
    bucket_ts: datetime
    denied: int
    auth: int


class BlockSummary(BaseModel):
    """Headline numbers for the filtered set -- the same filters as the
    grouped list, so the cards and the table always agree."""

    domains: int
    denied: int
    auth: int
    clients: int
    # Distinct logins; traffic without one isn't counted here.
    users: int
    branches: list[str]
    proxies: list[str]
    series: list[BlockSeriesPoint]
    # Proxy labels seen in the range, for the proxy filter (not narrowed by
    # the other filters, so it keeps offering every proxy).
    available_proxies: list[str]
