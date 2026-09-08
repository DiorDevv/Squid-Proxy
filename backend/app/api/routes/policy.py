from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_or_auditor
from app.core.config import get_settings
from app.schemas.policy import (
    ArchivingPolicy,
    CollectedField,
    DataPolicyResponse,
    RetentionWindows,
)
from app.services import retention_settings_service

router = APIRouter(prefix="/api", tags=["policy"], dependencies=[Depends(require_admin_or_auditor)])

# What a raw_events row actually holds (app/models/raw_event.py). Stated
# here, in code, so the policy surface can't drift from a hand-kept doc.
_COLLECTED_FIELDS = [
    CollectedField(name="timestamp", description="When the request was made (from the Squid log)."),
    CollectedField(name="client IP", description="The proxy client's source IP address."),
    CollectedField(
        name="username",
        description="The proxy-auth user, when proxy authentication is enabled (otherwise absent).",
    ),
    CollectedField(name="URL / domain", description="The requested URL and the host extracted from it."),
    CollectedField(name="HTTP method", description="GET, POST, CONNECT, etc."),
    CollectedField(
        name="result & status",
        description="Squid result code and HTTP status (whether it was served, cached, or denied).",
    ),
    CollectedField(name="bytes", description="Response size in bytes."),
    CollectedField(name="duration", description="How long the request took, in milliseconds."),
    CollectedField(
        name="content type", description="The response Content-Type reported by the origin, when present."
    ),
    CollectedField(name="branch", description="Which Squid source/site the line came from."),
]


@router.get("/policy", response_model=DataPolicyResponse)
async def read_data_policy(db: AsyncSession = Depends(get_db)) -> DataPolicyResponse:
    s = get_settings()
    retention = await retention_settings_service.get_settings_row(db)
    return DataPolicyResponse(
        purpose=s.DATA_PROCESSING_PURPOSE,
        controller=s.DATA_CONTROLLER,
        retention=RetentionWindows(
            raw_events_days=retention.raw_events_days,
            aggregates_days=s.RETENTION_DAYS_AGGREGATES,
            ops_aggregates_days=s.RETENTION_DAYS_OPS_AGGREGATES,
            archives_days=s.ARCHIVE_KEEP_DAYS,
            client_minute_rollup_after_hours=s.CLIENT_ROLLUP_AFTER_HOURS,
        ),
        archiving=ArchivingPolicy(
            enabled=s.ARCHIVE_ENABLED,
            encrypted=s.ARCHIVE_ENCRYPTION_KEY is not None,
            output_dir=s.ARCHIVE_OUTPUT_DIR,
        ),
        collected_fields=_COLLECTED_FIELDS,
    )
