from datetime import datetime

from pydantic import BaseModel

from app.models.export_job import ExportJobStatus


class ExportJobOut(BaseModel):
    id: str
    status: ExportJobStatus
    format: str
    since: datetime
    until: datetime
    blocked_only: bool
    branch: str | None
    row_count: int | None
    file_size_bytes: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
