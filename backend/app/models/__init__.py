"""Importing this package imports every model module, which is what
registers all ORM tables on ``Base.metadata``.

This is the single source of that list. Both places that need "every table
known" -- Alembic's ``env.py`` (for autogenerate / ``alembic check``) and
``db.init_db``'s ``create_all`` fallback -- import this package instead of
each keeping its own hand-maintained, drift-prone subset. A new model only
has to be added to the tuple below.
"""

from app.models import (
    alert_settings,
    anomaly_event,
    archive_run,
    audit_log,
    client_aggregate,
    client_category_aggregate,
    client_hourly_aggregate,
    domain_aggregate,
    domain_category,
    export_job,
    export_settings,
    minute_aggregate,
    ops_aggregate,
    raw_event,
    refresh_token,
    report_schedule_state,
    system_event,
    telegram_global_settings,
    telegram_link_code,
    totp_recovery_code,
    user,
    watchlist_entry,
)

__all__ = [
    "alert_settings",
    "anomaly_event",
    "archive_run",
    "audit_log",
    "client_aggregate",
    "client_category_aggregate",
    "client_hourly_aggregate",
    "domain_aggregate",
    "domain_category",
    "export_job",
    "export_settings",
    "minute_aggregate",
    "ops_aggregate",
    "raw_event",
    "refresh_token",
    "report_schedule_state",
    "system_event",
    "telegram_global_settings",
    "telegram_link_code",
    "totp_recovery_code",
    "user",
    "watchlist_entry",
]
