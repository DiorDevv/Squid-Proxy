from enum import Enum

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.schemas.common import EffectiveRange, resolve_range
from app.services.export_service import export_as_csv, export_as_json

router = APIRouter(prefix="/api", tags=["export"])


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


@router.get("/export", dependencies=[Depends(require_admin)])
async def export_events(
    effective_range: EffectiveRange = Depends(resolve_range),
    format: ExportFormat = Query(default=ExportFormat.CSV),
    blocked_only: bool = Query(default=False),
    branch: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    # Custom from_ts/to_ts ranges have no RangeParam label -- fall back to a
    # timestamp-based filename suffix so it's still descriptive.
    if effective_range.range:
        range_label = effective_range.range.value
    else:
        range_label = effective_range.until.date().isoformat()
    if format == ExportFormat.CSV:
        body = await export_as_csv(db, effective_range.since, effective_range.until, blocked_only, branch)
        media_type = "text/csv"
        filename = f"squid-events-{range_label}.csv"
    else:
        body = await export_as_json(db, effective_range.since, effective_range.until, blocked_only, branch)
        media_type = "application/json"
        filename = f"squid-events-{range_label}.json"

    return PlainTextResponse(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
