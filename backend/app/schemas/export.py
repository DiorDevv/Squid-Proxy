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
    domain: str | None
    category: str | None
    client_ip: str | None
    columns: list[str] | None
    row_count: int | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    share_link_active: bool
    share_link_expires_at: datetime | None


class ExportShareLinkOut(BaseModel):
    """Response for POST /export/jobs/{id}/share -- the only place the raw
    token is ever returned (see export_job_service.to_out's docstring on
    share_link_active for why ExportJobOut never carries it)."""

    token: str
    expires_at: datetime
    download_url: str
