import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import health, metrics
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_var
from app.core.rate_limit import limiter
from app.services.log_parser import ParsedEvent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting Squid Dashboard backend", extra={"environment": settings.ENVIRONMENT})

    from app.models.db import init_db

    await init_db()

    from app.services.export_job_service import reconcile_orphaned_jobs

    orphaned_count = await reconcile_orphaned_jobs()
    if orphaned_count:
        logger.warning("Marked %d export job(s) failed -- interrupted by a previous restart", orphaned_count)

    from app.services.auth_bootstrap import bootstrap_admin_user

    await bootstrap_admin_user()

    from app.core.security import LoginThrottle, MfaChallengeStore, WsTicketStore
    from app.services.event_store import RingBuffer
    from app.services.log_tailer import LogTailer
    from app.services.ws_manager import WebSocketManager

    ring_buffer = RingBuffer(max_events=settings.RING_BUFFER_MAX_EVENTS)
    ws_manager = WebSocketManager()
    ws_ticket_store = WsTicketStore(ttl_seconds=settings.WS_TICKET_EXPIRE_SECONDS)
    mfa_challenge_store = MfaChallengeStore()
    login_throttle = LoginThrottle(
        failure_threshold=settings.LOGIN_ACCOUNT_FAILURE_THRESHOLD,
        failure_window_seconds=settings.LOGIN_ACCOUNT_FAILURE_WINDOW_SECONDS,
        throttled_interval_seconds=settings.LOGIN_ACCOUNT_THROTTLED_INTERVAL_SECONDS,
    )
    app.state.ring_buffer = ring_buffer
    app.state.ws_manager = ws_manager
    app.state.ws_ticket_store = ws_ticket_store
    app.state.mfa_challenge_store = mfa_challenge_store
    app.state.login_throttle = login_throttle

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
            state_dir=settings.LOG_TAILER_STATE_DIR,
        )
    app.state.log_tailers = log_tailers
    for tailer in log_tailers.values():
        tailer.start()

    from app.services.aggregator import Aggregator

    def _checkpoint_tailers() -> None:
        # Called by Aggregator right after a flush's commit() succeeds --
        # only then are the events already read by these tailers durably
        # in the database, and only then is it safe for each tailer to
        # persist how far it's read to disk (see LogTailer's module
        # docstring and checkpoint() for why persisting any earlier could
        # silently lose events across a crash).
        for tailer in log_tailers.values():
            tailer.checkpoint()

    aggregator = Aggregator(
        ring_buffer=ring_buffer,
        interval_seconds=settings.AGGREGATION_INTERVAL_SECONDS,
        on_flush_committed=_checkpoint_tailers,
    )
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

    from app.services.uncategorized_domain_monitor import UncategorizedDomainMonitorJob

    uncategorized_domain_monitor = UncategorizedDomainMonitorJob(
        interval_seconds=settings.UNCATEGORIZED_DOMAIN_MONITOR_INTERVAL_SECONDS
    )
    app.state.uncategorized_domain_monitor = uncategorized_domain_monitor
    uncategorized_domain_monitor.start()

    from app.services.watchlist_monitor import WatchlistMonitorJob

    watchlist_monitor = WatchlistMonitorJob(interval_seconds=settings.WATCHLIST_MONITOR_INTERVAL_SECONDS)
    app.state.watchlist_monitor = watchlist_monitor
    watchlist_monitor.start()

    from app.services.undownloaded_export_monitor import UndownloadedExportMonitorJob

    undownloaded_export_monitor = UndownloadedExportMonitorJob(
        interval_seconds=settings.UNDOWNLOADED_EXPORT_MONITOR_INTERVAL_SECONDS
    )
    app.state.undownloaded_export_monitor = undownloaded_export_monitor
    undownloaded_export_monitor.start()

    from app.services.report_scheduler import ReportScheduler

    report_scheduler = ReportScheduler(interval_seconds=settings.REPORT_SCHEDULER_CHECK_INTERVAL_SECONDS)
    app.state.report_scheduler = report_scheduler
    report_scheduler.start()

    from app.services.telegram_link_poller import TelegramLinkPollerJob

    telegram_link_poller = TelegramLinkPollerJob()
    app.state.telegram_link_poller = telegram_link_poller
    telegram_link_poller.start()

    from app.services.ut1_scheduler import Ut1BlacklistScheduler

    ut1_scheduler = Ut1BlacklistScheduler(interval_seconds=settings.UT1_REFRESH_INTERVAL_SECONDS)
    app.state.ut1_scheduler = ut1_scheduler
    ut1_scheduler.start()

    # One place GET /api/system-health enumerates every IntervalJob's
    # health (alive / last error / consecutive failures) without a
    # hand-kept list of app.state attribute names.
    app.state.background_jobs = {
        job.job_name: job
        for job in (
            retention_job,
            archive_scheduler,
            category_usage_monitor,
            quota_monitor,
            uncategorized_domain_monitor,
            watchlist_monitor,
            undownloaded_export_monitor,
            report_scheduler,
            telegram_link_poller,
            ut1_scheduler,
        )
    }

    try:
        yield
    finally:
        logger.info("Shutting down Squid Dashboard backend")
        # Ordering that matters: every tailer must stop feeding the ring
        # buffer *before* the aggregator does its final flush+checkpoint,
        # otherwise a late event slips in after the last checkpoint and is
        # re-read on restart (harmless -- the upsert is idempotent -- but
        # avoidable). Everything after that is mutually independent, so it's
        # shut down concurrently rather than as a ~13-deep serial await
        # chain: each .stop() is already individually bounded (5-10s, see
        # IntervalJob.stop / Aggregator.stop), but serially that summed to
        # over a minute, well past a typical container stop-grace before
        # SIGKILL.
        await asyncio.gather(*(tailer.stop() for tailer in log_tailers.values()))
        await aggregator.stop()
        await asyncio.gather(
            retention_job.stop(),
            archive_scheduler.stop(),
            category_usage_monitor.stop(),
            quota_monitor.stop(),
            report_scheduler.stop(),
            ut1_scheduler.stop(),
            uncategorized_domain_monitor.stop(),
            undownloaded_export_monitor.stop(),
            watchlist_monitor.stop(),
            telegram_link_poller.stop(),
        )


def _handle_new_event(app: FastAPI, event: ParsedEvent) -> None:
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
        version="0.3.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    # slowapi's own handler is typed narrowly for RateLimitExceeded, while
    # Starlette's registry wants a handler typed for the general Exception
    # (it dispatches by the registered exception *class* passed as the first
    # argument here, not by the handler's own annotation) -- a structural
    # mismatch between the two libraries' stubs, not a real bug; this is
    # exactly how slowapi's own docs wire it up.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Cap + strip newlines so a client-supplied value can't bloat or
        # line-inject a log record (the JSON formatter escapes newlines
        # anyway, but there's no reason to carry an arbitrary-length header
        # around).
        raw_id = request.headers.get("X-Request-ID", "")
        request_id = raw_id.replace("\n", "").replace("\r", "")[:128] or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        # Cheap, response-shape-independent hardening headers. HSTS/CSP are
        # deliberately not here -- TLS terminates at the reverse proxy (this
        # app may legitimately serve plain HTTP behind it) and CSP is a
        # concern for the HTML frontend, not this JSON/file API.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Authenticated API + file downloads (exports, share links): never
        # let a shared cache hold a response. Endpoints that are fine to
        # cache set their own Cache-Control before this runs.
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(metrics.router)

    from app.api.routes import (
        alert_settings,
        analytics,
        audit,
        auth,
        branches,
        clients,
        domain_categories,
        domains,
        events,
        export,
        export_settings,
        insights,
        policy,
        reports,
        subject_access,
        summary,
        system_health,
        timeseries,
        users,
        watchlist,
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
    app.include_router(export_settings.router)
    app.include_router(users.router)
    app.include_router(audit.router)
    app.include_router(policy.router)
    app.include_router(insights.router)
    app.include_router(alert_settings.router)
    app.include_router(analytics.router)
    app.include_router(reports.router)
    app.include_router(watchlist.router)
    app.include_router(subject_access.router)
    app.include_router(system_health.router)
    app.include_router(ws.router)

    return app


app = create_app()
