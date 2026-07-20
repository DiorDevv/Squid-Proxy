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

    aggregator = getattr(request.app.state, "aggregator", None)
    backlog_ratio = round(aggregator.backlog_ratio, 3) if aggregator else 0.0
    events_likely_lost = bool(aggregator and aggregator.events_likely_lost)

    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "log_tailer_alive": tailer_alive,
        "log_lines_seen": lines_seen,
        "log_lines_parsed": lines_parsed,
        "log_parse_failure_rate": parse_failure_rate,
        # If the aggregator can't keep up with incoming traffic, the ring
        # buffer's eviction can drop events before they're ever persisted --
        # see Aggregator.events_likely_lost/backlog_ratio. Surfaced here so
        # it's visible to monitoring instead of only appearing as a WARNING/
        # ERROR log line an operator has to go looking for.
        "aggregator_backlog_ratio": backlog_ratio,
        "aggregator_events_likely_lost": events_likely_lost,
    }
