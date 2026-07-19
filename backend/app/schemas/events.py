from datetime import datetime

from pydantic import BaseModel


class EventOut(BaseModel):
    id: int
    timestamp: datetime
    client_ip: str
    action: str
    status_code: int
    method: str
    url: str
    domain: str | None
    user: str | None
    bytes: int
    blocked: bool
