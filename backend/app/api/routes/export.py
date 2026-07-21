from enum import Enum

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import require_admin
from app.schemas.common import EffectiveRange, resolve_range
from app.services.export_service import download_csv, download_json

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
) -> StreamingResponse:
    # Custom from_ts/to_ts ranges have no RangeParam label -- fall back to a
    # timestamp-based filename suffix so it's still descriptive.
    if effective_range.range:
        range_label = effective_range.range.value
    else:
        range_label = effective_range.until.date().isoformat()

    # Streamed (see export_service.download_csv/json), so a full range --
    # even one covering millions of rows, e.g. the 7d preset at real
    # traffic volumes -- downloads without being capped or built in memory
    # server-side.
    if format == ExportFormat.CSV:
        body = download_csv(effective_range.since, effective_range.until, blocked_only, branch)
        media_type = "text/csv"
        filename = f"squid-events-{range_label}.csv"
    else:
        body = download_json(effective_range.since, effective_range.until, blocked_only, branch)
        media_type = "application/json"
        filename = f"squid-events-{range_label}.json"

    return StreamingResponse(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
