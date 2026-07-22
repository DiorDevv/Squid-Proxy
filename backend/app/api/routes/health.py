from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


def _failure_rate(lines_seen: int, lines_parsed: int) -> float | None:
    # None (not 0.0) when nothing has been read yet -- "no data seen" and
    # "everything failed to parse" must stay distinguishable, since the
    # first one is just an idle/new install and the second is a real
    # logformat mismatch.
    return None if lines_seen == 0 else round(1 - (lines_parsed / lines_seen), 3)


@router.get("/api/health", response_model=None)
async def health(request: Request, strict: bool = False) -> dict | JSONResponse:
    """`strict=true` returns HTTP 503 instead of 200 when the tailer is down
    or events are being dropped -- for infra healthchecks (docker-compose's
    `backend` healthcheck, a load balancer/orchestrator readiness probe) that
    key off status code alone. Defaults to false (always 200) because the
    frontend's own health banner (see useHealthCheck.ts/LogHealthBanner.tsx)
    polls this same endpoint to *render* these same conditions -- if this
    default flipped, a non-2xx response would make apiFetch throw instead of
    returning the body, and the banner that's supposed to explain the
    problem would just silently stop rendering at exactly the moment it
    matters most.
    """
    tailers = getattr(request.app.state, "log_tailers", {})

    log_sources = [
        {
            "branch": branch,
            "alive": tailer.is_alive,
            "lines_seen": tailer.lines_seen,
            "lines_parsed": tailer.lines_parsed,
            "parse_failure_rate": _failure_rate(tailer.lines_seen, tailer.lines_parsed),
        }
        for branch, tailer in tailers.items()
    ]

    # Aggregate across every source -- kept as the top-level fields for
    # backward compatibility with the existing single-source dashboard
    # banner check; log_sources above is where a per-branch breakdown lives.
    tailer_alive = bool(tailers) and all(tailer.is_alive for tailer in tailers.values())
    lines_seen = sum(tailer.lines_seen for tailer in tailers.values())
    lines_parsed = sum(tailer.lines_parsed for tailer in tailers.values())
    parse_failure_rate = _failure_rate(lines_seen, lines_parsed)

    aggregator = getattr(request.app.state, "aggregator", None)
    backlog_ratio = round(aggregator.backlog_ratio, 3) if aggregator else 0.0
    events_likely_lost = bool(aggregator and aggregator.events_likely_lost)

    retention_job = getattr(request.app.state, "retention_job", None)
    unarchived_branches = list(retention_job.unarchived_branches) if retention_job else []

    payload = {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "log_tailer_alive": tailer_alive,
        "log_lines_seen": lines_seen,
        "log_lines_parsed": lines_parsed,
        "log_parse_failure_rate": parse_failure_rate,
        "log_sources": log_sources,
        # If the aggregator can't keep up with incoming traffic, the ring
        # buffer's eviction can drop events before they're ever persisted --
        # see Aggregator.events_likely_lost/backlog_ratio. Surfaced here so
        # it's visible to monitoring instead of only appearing as a WARNING/
        # ERROR log line an operator has to go looking for.
        "aggregator_backlog_ratio": backlog_ratio,
        "aggregator_events_likely_lost": events_likely_lost,
        # Branches whose raw_events were just permanently purged by the last
        # retention run without ever being archived (see RetentionJob.
        # purge()/_find_unarchived_branches) -- empty in the normal case
        # where scripts/archive_weekly_export.py is running on schedule.
        "unarchived_purge_branches": unarchived_branches,
    }

    # Not unarchived_branches -- that's a data-retention warning an operator
    # needs to see, not a "this instance is broken" signal a healthcheck
    # should act on (restarting the container wouldn't fix it either way).
    is_unhealthy = not tailer_alive or events_likely_lost
    if strict and is_unhealthy:
        return JSONResponse(status_code=503, content=payload)
    return payload
