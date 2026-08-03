"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "CHANGE_ME_INSECURE_DEV_SECRET"
# Matches the placeholder both .env.example (root, for docker-compose) and
# backend/.env.example ship for ADMIN_PASSWORD -- see
# _reject_insecure_production_secret.
INSECURE_DEFAULT_ADMIN_PASSWORD = "CHANGE_ME_STRONG_PASSWORD"
# docker-compose.yml's own POSTGRES_PASSWORD fallback -- there's no
# dedicated POSTGRES_PASSWORD Settings field (the app only ever sees the
# already-assembled DATABASE_URL), so this is checked as a substring of it
# instead. Requiring POSTGRES_PASSWORD to be set at all is handled at the
# docker-compose level (`:?...` instead of a silent `:-` fallback); this is
# the same defense-in-depth JWT_SECRET/ADMIN_PASSWORD get from being checked
# here too, in case DATABASE_URL is ever set directly instead.
INSECURE_DEFAULT_POSTGRES_PASSWORD = "squid_dev_password"

# Branch tag used when no LOG_SOURCES is configured -- keeps single-branch
# deployments (the common case) working with zero config changes, since
# LOG_FILE_PATH alone still produces one implicit branch under this name.
DEFAULT_BRANCH = "default"


class LogSource(BaseModel):
    """One Squid access.log to tail, tagged with the branch/site it belongs
    to. See Settings.effective_log_sources."""

    branch: str
    path: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Squid log source(s) ---
    # LOG_FILE_PATH is the single-branch default. For multiple branches (each
    # with its own Squid access.log already landing as a local file on this
    # server -- e.g. shipped in via syslog centralization), set LOG_SOURCES
    # instead: a JSON array of {"branch": "...", "path": "..."} objects, one
    # per branch. LOG_FILE_PATH is then ignored in favor of LOG_SOURCES; see
    # effective_log_sources for the fallback logic.
    LOG_FILE_PATH: str = "/var/log/squid/access.log"
    LOG_SOURCES: list[LogSource] = Field(default_factory=list)
    LOG_TAILER_POLL_INTERVAL_SECONDS: float = 0.75
    LOG_TAILER_BACKOFF_MAX_SECONDS: float = 30.0
    # Where each branch's tailer persists its read position (inode + byte
    # offset), so a restart resumes exactly where it left off instead of
    # silently skipping whatever Squid wrote while the process was down --
    # see app/services/log_tailer.py's module docstring.
    LOG_TAILER_STATE_DIR: str = "./log_tailer_state"

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./squid_dashboard.db"
    # Ignored for sqlite -- a single local file gets no benefit from a
    # bigger connection pool (see app/models/db.py). Defaults match
    # SQLAlchemy's own library defaults exactly, so this is a no-op until a
    # deployment's real concurrency needs more. What actually drives pool
    # contention isn't proxy-client count (Squid clients never touch the
    # DB) but the ~9 independent background jobs in main.py plus concurrent
    # dashboard/API traffic -- for a large deployment (tens of thousands of
    # proxied clients, correspondingly larger tables and longer-held
    # connections per query), DATABASE_POOL_SIZE=10 / DATABASE_MAX_OVERFLOW=20
    # (30-connection ceiling) is a reasonable starting point; see "Sizing
    # for a large client count" in ARCHITECTURE.md.
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # --- In-memory ring buffer ---
    # Sized for demo/small-deployment scale by default. At high sustained
    # ingest rates, buffer capacity ÷ peak events/sec is the runway before
    # AGGREGATION_INTERVAL_SECONDS below has to keep up or events start
    # being silently dropped (surfaced via Aggregator.backlog_ratio /
    # /api/health's aggregator_backlog_ratio, not actually silent -- see
    # aggregator.py) -- see "Sizing for a large client count" in
    # ARCHITECTURE.md for a worked example and recommended values.
    RING_BUFFER_MAX_EVENTS: int = 500_000

    # --- Retention ---
    RETENTION_DAYS_RAW_EVENTS: int = 7
    RETENTION_DAYS_AGGREGATES: int = 400
    # How often the ring buffer flushes to DB aggregates. Lower = less
    # runway needed in RING_BUFFER_MAX_EVENTS above per flush cycle, at the
    # cost of more frequent (still bulk-upsert, see db_upsert.py) writes.
    AGGREGATION_INTERVAL_SECONDS: int = 60
    RETENTION_PURGE_INTERVAL_SECONDS: int = 3600
    # client_minute_aggregates rows older than this get compressed into
    # client_hourly_aggregates and deleted (see retention.py) -- otherwise
    # minute-granular rows accumulate for the full RETENTION_DAYS_AGGREGATES
    # window, which is what makes wide-range client queries slow at scale.
    CLIENT_ROLLUP_AFTER_HOURS: int = 48

    # --- Automatic raw-event archiving (see app/services/archive_service.py,
    # app/services/archive_scheduler.py) -- runs before
    # RETENTION_DAYS_RAW_EVENTS purges the same data, so it isn't lost for
    # good. Defaults on (unlike REPORT_SCHEDULE below, which defaults
    # disabled): this only touches local disk, no external credentials
    # needed, so there's little downside to it just working out of the box:
    # set to false to manage this fully yourself instead (e.g. via
    # scripts/archive_weekly_export.py on your own cron/systemd timer).
    ARCHIVE_ENABLED: bool = True
    ARCHIVE_OUTPUT_DIR: str = "./archives"
    ARCHIVE_KEEP_DAYS: int = 365
    # Each archive() call re-covers a deliberately-overlapping ~7-day window
    # (see that function's docstring), so calling it isn't cheap/incremental
    # -- these are two different cadences, same split as REPORT_SCHEDULE /
    # REPORT_SCHEDULER_CHECK_INTERVAL_SECONDS below: how often to check
    # whether a run is due (cheap, reads already-persisted ArchiveRun rows)
    # vs. how long between actually calling archive() (expensive).
    ARCHIVE_CHECK_INTERVAL_SECONDS: int = 3600
    ARCHIVE_MIN_INTERVAL_SECONDS: int = 604800

    # --- Background export jobs (see api/routes/export.py, ExportJob) ---
    EXPORT_JOBS_DIR: str = "./export_jobs"
    # Cleanup policy (how long a result file is kept, or whether it's
    # deleted right after download instead) is admin-configurable at
    # runtime via GET/PUT /api/export-settings, not here -- see
    # app/models/export_settings.py.
    # A wide range at real traffic volumes can produce a multi-hundred-MB
    # file and run for minutes; nothing stops several admins (or several
    # browser tabs) from kicking off that many at once, and EXPORT_JOBS_DIR
    # has no size cap of its own. This bounds how many PENDING/RUNNING jobs
    # can exist at the same time so that can't fill the disk.
    EXPORT_JOB_MAX_CONCURRENT: int = 3
    # How long a share link (see export_job_service.create_share_link) stays
    # valid for once an admin issues one -- deliberately an env var, not an
    # admin-tunable setting like ExportSettings' cleanup policy: this is a
    # security boundary (how long a no-login download stays reachable), the
    # same category as ACCESS_TOKEN_EXPIRE_MINUTES above, not business policy.
    EXPORT_SHARE_LINK_TTL_HOURS: int = 24

    # --- Time-spent-per-domain estimation ---
    # Consecutive requests to the same domain more than this many minutes
    # apart are treated as separate sessions (e.g. a lunch break isn't
    # counted as "time spent" on whatever site was open before it).
    SESSION_GAP_MINUTES: int = 30

    # --- Auth / JWT ---
    JWT_SECRET: str = INSECURE_DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    WS_TICKET_EXPIRE_SECONDS: int = 30

    # --- Bootstrap admin (first-boot convenience only) ---
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Rate limiting ---
    LOGIN_RATE_LIMIT: str = "5/minute"
    SENSITIVE_ACTION_RATE_LIMIT: str = "20/minute"

    # --- Insights / anomaly detection ---
    INSIGHTS_PROVIDER: str = "noop"

    # --- Alerting (optional; no-op unless ALERT_WEBHOOK_URL is set) ---
    ALERT_WEBHOOK_URL: str | None = None
    ALERT_MIN_SEVERITY: str = "high"

    # --- Operator-facing infra-failure alerts (see app/services/
    # ops_alerting.py) -- distinct from the traffic-anomaly alerting above.
    # Falls back to ALERT_WEBHOOK_URL if unset, so a single-webhook operator
    # needs zero new config; set this separately to route infra failures
    # (log tailer down, backup failed, a background job erroring out) to a
    # different channel than traffic anomalies (e.g. PagerDuty vs. Slack).
    OPS_ALERT_WEBHOOK_URL: str | None = None

    # --- Error tracking (optional; no-op unless SENTRY_DSN is set) --
    # everywhere else unhandled exceptions only ever go to stdout (see
    # core/exceptions.py's catch-all handler) -- nothing forwards them
    # anywhere someone's necessarily watching. Needs your own Sentry (or
    # Sentry-compatible, e.g. GlitchTip) project/DSN to actually activate.
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # --- Category/quota monitor jobs (thresholds are admin-configurable at
    # runtime via /api/alert-settings; these only control how often the
    # background jobs re-check) ---
    CATEGORY_MONITOR_INTERVAL_SECONDS: int = 3600
    QUOTA_MONITOR_INTERVAL_SECONDS: int = 3600
    # How often to check for high-traffic uncategorized domains (see
    # app/services/uncategorized_domain_monitor.py) -- the per-branch
    # request-count threshold that actually gates whether this raises
    # anything is admin-configurable at runtime via /api/alert-settings,
    # same as the two intervals above.
    UNCATEGORIZED_DOMAIN_MONITOR_INTERVAL_SECONDS: int = 86400
    # How often to check for undownloaded export jobs (see
    # app/services/undownloaded_export_monitor.py) -- the threshold that
    # actually gates whether this raises anything
    # (warn_undownloaded_after_hours) is admin-configurable at runtime via
    # /api/export-settings, same as the interval above.
    UNDOWNLOADED_EXPORT_MONITOR_INTERVAL_SECONDS: int = 3600

    # --- UT1 bulk domain blacklist (optional; see app/services/
    # ut1_blacklist.py). Off by default -- this reaches a third-party
    # (French university) server over the internet at runtime, which
    # shouldn't happen silently for a compliance/security tool. ---
    UT1_ENABLED: bool = False
    UT1_MIRROR_URL: str = "https://dsi.ut-capitole.fr/blacklists/download/blacklists.tar.gz"
    UT1_DATA_DIR: str = "./ut1_blacklist_data"
    UT1_REFRESH_INTERVAL_SECONDS: int = 604800

    # --- Scheduled email reports (optional; no-op unless REPORT_RECIPIENTS
    # is set) ---
    REPORT_SCHEDULE: str = "disabled"  # "disabled" | "daily" | "weekly"
    REPORT_RECIPIENTS: list[str] = Field(default_factory=list)
    REPORT_SCHEDULER_CHECK_INTERVAL_SECONDS: int = 900
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_ADDRESS: str | None = None
    SMTP_USE_TLS: bool = True

    @property
    def effective_log_sources(self) -> list[LogSource]:
        """LOG_SOURCES if configured; otherwise a single implicit source
        built from LOG_FILE_PATH under DEFAULT_BRANCH, so existing
        single-branch deployments don't need any config change."""
        if self.LOG_SOURCES:
            return self.LOG_SOURCES
        return [LogSource(branch=DEFAULT_BRANCH, path=self.LOG_FILE_PATH)]

    @model_validator(mode="after")
    def _reject_insecure_production_secret(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self
        if self.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is still the insecure default. Set a real secret "
                "(python3 -c \"import secrets; print(secrets.token_urlsafe(48))\") "
                "before running with ENVIRONMENT=production."
            )
        if self.ADMIN_PASSWORD == INSECURE_DEFAULT_ADMIN_PASSWORD:
            raise ValueError(
                "ADMIN_PASSWORD is still the .env.example placeholder. Set a real "
                "password before running with ENVIRONMENT=production."
            )
        if INSECURE_DEFAULT_POSTGRES_PASSWORD in self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL still contains the insecure default POSTGRES_PASSWORD "
                "(squid_dev_password). Set a real POSTGRES_PASSWORD before running "
                "with ENVIRONMENT=production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
