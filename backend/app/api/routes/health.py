from datetime import UTC, datetime

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(request: Request) -> dict:
    tailer = getattr(request.app.state, "log_tailer", None)
    tailer_alive = bool(tailer and tailer.is_alive)

    lines_seen = tailer.lines_seen if tailer else 0
    lines_parsed = tailer.lines_parsed if tailer else 0
    # None (not 0.0) when nothing has been read yet -- "no data seen" and
    # "everything failed to parse" must stay distinguishable, since the
    # first one is just an idle/new install and the second is a real
    # logformat mismatch.
    parse_failure_rate = None if lines_seen == 0 else round(1 - (lines_parsed / lines_seen), 3)

    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "log_tailer_alive": tailer_alive,
        "log_lines_seen": lines_seen,
        "log_lines_parsed": lines_parsed,
        "log_parse_failure_rate": parse_failure_rate,
    }
