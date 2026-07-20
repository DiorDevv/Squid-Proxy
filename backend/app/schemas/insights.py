from datetime import datetime

from pydantic import BaseModel

from app.models.anomaly_event import AnomalySeverity


class AnomalyEventOut(BaseModel):
    id: str
    generated_at: datetime
    title: str
    description: str
    severity: AnomalySeverity
    client_ip: str | None
    domain: str | None
    branch: str
