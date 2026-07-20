"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "CHANGE_ME_INSECURE_DEV_SECRET"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Squid log source ---
    LOG_FILE_PATH: str = "/var/log/squid/access.log"
    LOG_TAILER_POLL_INTERVAL_SECONDS: float = 0.75
    LOG_TAILER_BACKOFF_MAX_SECONDS: float = 30.0

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./squid_dashboard.db"

    # --- In-memory ring buffer ---
    RING_BUFFER_MAX_EVENTS: int = 500_000

    # --- Retention ---
    RETENTION_DAYS_RAW_EVENTS: int = 7
    RETENTION_DAYS_AGGREGATES: int = 400
    AGGREGATION_INTERVAL_SECONDS: int = 60
    RETENTION_PURGE_INTERVAL_SECONDS: int = 3600
    # client_minute_aggregates rows older than this get compressed into
    # client_hourly_aggregates and deleted (see retention.py) -- otherwise
    # minute-granular rows accumulate for the full RETENTION_DAYS_AGGREGATES
    # window, which is what makes wide-range client queries slow at scale.
    CLIENT_ROLLUP_AFTER_HOURS: int = 48

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

    # --- Category/quota monitor jobs (thresholds are admin-configurable at
    # runtime via /api/alert-settings; these only control how often the
    # background jobs re-check) ---
    CATEGORY_MONITOR_INTERVAL_SECONDS: int = 3600
    QUOTA_MONITOR_INTERVAL_SECONDS: int = 3600

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

    @model_validator(mode="after")
    def _reject_insecure_production_secret(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is still the insecure default. Set a real secret "
                "(python3 -c \"import secrets; print(secrets.token_urlsafe(48))\") "
                "before running with ENVIRONMENT=production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
