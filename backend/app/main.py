import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import health
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_var
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting Squid Dashboard backend", extra={"environment": settings.ENVIRONMENT})

    from app.models.db import init_db

    await init_db()

    from app.services.export_job_service import reconcile_orphaned_jobs

    orphaned_count = await reconcile_orphaned_jobs()
    if orphaned_count:
        logger.warning(
            "Marked %d export job(s) failed -- interrupted by a previous restart", orphaned_count
        )

    from app.services.auth_bootstrap import bootstrap_admin_user

    await bootstrap_admin_user()

    from app.core.security import WsTicketStore
    from app.services.event_store import RingBuffer
    from app.services.log_tailer import LogTailer
    from app.services.ws_manager import WebSocketManager

    ring_buffer = RingBuffer(max_events=settings.RING_BUFFER_MAX_EVENTS)
    ws_manager = WebSocketManager()
    ws_ticket_store = WsTicketStore(ttl_seconds=settings.WS_TICKET_EXPIRE_SECONDS)
    app.state.ring_buffer = ring_buffer
    app.state.ws_manager = ws_manager
    app.state.ws_ticket_store = ws_ticket_store

    # One LogTailer per configured branch/log source (see
    # Settings.effective_log_sources) -- all feed the same, single, shared
    # ring buffer, since this stays a single-process deployment (see
    # ARCHITECTURE.md); only the ingestion side fans out.
    log_tailers: dict[str, LogTailer] = {}
    for source in settings.effective_log_sources:
        log_tailers[source.branch] = LogTailer(
            path=source.path,
            on_event=lambda event: _handle_new_event(app, event),
            branch=source.branch,
            poll_interval=settings.LOG_TAILER_POLL_INTERVAL_SECONDS,
            backoff_max=settings.LOG_TAILER_BACKOFF_MAX_SECONDS,
        )
    app.state.log_tailers = log_tailers
    for tailer in log_tailers.values():
        tailer.start()

    from app.services.aggregator import Aggregator

    aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=settings.AGGREGATION_INTERVAL_SECONDS)
    app.state.aggregator = aggregator
    aggregator.start()

    from app.services.retention import RetentionJob

    retention_job = RetentionJob(interval_seconds=settings.RETENTION_PURGE_INTERVAL_SECONDS)
    app.state.retention_job = retention_job
    retention_job.start()

    from app.services.archive_scheduler import ArchiveScheduler

    archive_scheduler = ArchiveScheduler(
        check_interval_seconds=settings.ARCHIVE_CHECK_INTERVAL_SECONDS,
        min_interval_seconds=settings.ARCHIVE_MIN_INTERVAL_SECONDS,
    )
    app.state.archive_scheduler = archive_scheduler
    archive_scheduler.start()

    from app.services.category_usage_monitor import CategoryUsageMonitorJob

    category_usage_monitor = CategoryUsageMonitorJob(
        interval_seconds=settings.CATEGORY_MONITOR_INTERVAL_SECONDS
    )
    app.state.category_usage_monitor = category_usage_monitor
    category_usage_monitor.start()

    from app.services.quota_monitor import QuotaMonitorJob

    quota_monitor = QuotaMonitorJob(interval_seconds=settings.QUOTA_MONITOR_INTERVAL_SECONDS)
    app.state.quota_monitor = quota_monitor
    quota_monitor.start()

    from app.services.report_scheduler import ReportScheduler

    report_scheduler = ReportScheduler(interval_seconds=settings.REPORT_SCHEDULER_CHECK_INTERVAL_SECONDS)
    app.state.report_scheduler = report_scheduler
    report_scheduler.start()

    try:
        yield
    finally:
        logger.info("Shutting down Squid Dashboard backend")
        for tailer in log_tailers.values():
            await tailer.stop()
        await aggregator.stop()
        await retention_job.stop()
        await archive_scheduler.stop()
        await category_usage_monitor.stop()
        await quota_monitor.stop()
        await report_scheduler.stop()


def _handle_new_event(app: FastAPI, event) -> None:
    stored = app.state.ring_buffer.append(event)
    app.state.ws_manager.broadcast_nowait(stored)


def create_app() -> FastAPI:
    settings = get_settings()

    if settings.SENTRY_DSN:
        import sentry_sdk

        # No integrations= list -- sentry_sdk auto-detects FastAPI/Starlette
        # (and the stdlib logging handler, so ERROR-level log lines like the
        # ones core/exceptions.py's catch-all handler already emits get
        # captured too, not just raised exceptions) once sentry-sdk[fastapi]
        # is installed. traces_sample_rate defaults to 0.0 (errors only, no
        # performance tracing) -- a deliberate opt-in, not a hidden default.
        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE)

    app = FastAPI(
        title="Squid Proxy Log Analytics API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)

    app.include_router(health.router)

    from app.api.routes import (
        alert_settings,
        audit,
        auth,
        branches,
        clients,
        domain_categories,
        domains,
        events,
        export,
        insights,
        reports,
        summary,
        timeseries,
        users,
        ws,
    )

    app.include_router(auth.router)
    app.include_router(branches.router)
    app.include_router(summary.router)
    app.include_router(timeseries.router)
    app.include_router(domains.router)
    app.include_router(domain_categories.router)
    app.include_router(clients.router)
    app.include_router(events.router)
    app.include_router(export.router)
    app.include_router(users.router)
    app.include_router(audit.router)
    app.include_router(insights.router)
    app.include_router(alert_settings.router)
    app.include_router(reports.router)
    app.include_router(ws.router)

    return app


app = create_app()
