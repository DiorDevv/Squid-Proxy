from datetime import datetime

from pydantic import BaseModel


class ReportStatusOut(BaseModel):
    schedule: str
    recipients_configured: bool
    smtp_configured: bool
    last_sent_at: datetime | None


class SendReportNowResponse(BaseModel):
    sent: bool
    since: datetime
    until: datetime
