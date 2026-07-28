from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.export_settings import ExportCleanupMode


class ExportSettingsOut(BaseModel):
    cleanup_mode: ExportCleanupMode
    retention_hours: int
    warn_undownloaded_after_hours: int | None
    updated_at: datetime


class UpdateExportSettingsRequest(BaseModel):
    cleanup_mode: ExportCleanupMode
    retention_hours: int
    warn_undownloaded_after_hours: int | None = None

    @field_validator("retention_hours")
    @classmethod
    def _retention_hours_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("retention_hours must be positive.")
        return value
