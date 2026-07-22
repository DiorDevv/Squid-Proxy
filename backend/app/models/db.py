"""Async SQLAlchemy engine/session setup.

Driver is selected purely from the `DATABASE_URL` scheme, so switching from
the SQLite default to Postgres is a one-line env var change with no code
changes (see ARCHITECTURE.md).
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_async_engine(_settings.DATABASE_URL, echo=False, future=True)

if _settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    # Import models so they're registered on Base.metadata before create_all.
    from app.models import (  # noqa: F401
        anomaly_event,
        archive_run,
        audit_log,
        client_aggregate,
        client_category_aggregate,
        client_hourly_aggregate,
        domain_aggregate,
        domain_category,
        export_job,
        minute_aggregate,
        raw_event,
        refresh_token,
        user,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Deliberately outside the create_all transaction: each statement below
    # runs in its own connection/transaction so a failure on one (or on a
    # database with pre-existing duplicate rows) can't poison the others or
    # roll back the schema that create_all just committed.
    await _ensure_aggregate_unique_indexes(engine)


async def _ensure_aggregate_unique_indexes(bind_engine=None) -> None:
    """Idempotently add the aggregate-table unique indexes for installs that
    only ever run `create_all` (never Alembic) -- see migration
    466aaa85c9f3_aggregate_unique_constraints for the full rationale.
    `create_all` alone won't add these to a table that already exists, and
    the expression-based client index can't be declared in the ORM model at
    all, so both are applied here as plain idempotent DDL.

    Also called by tests (see conftest.py's db_engine fixture, passing its
    own in-memory engine) so the ON CONFLICT target that
    app/services/db_upsert.py relies on for client_minute_aggregates exists
    against test databases too, not just real ones built via init_db().
    """
    bind_engine = bind_engine if bind_engine is not None else engine
    statements = [
        # branch joined every one of these keys (see migration
        # a4f7c2e9b1d6_branch_dimension) -- an existing install that only
        # ever runs create_all (never Alembic) still won't have the `branch`
        # column itself without that migration (create_all never ALTERs an
        # existing table), so these DBAPIErrors on such installs are
        # expected and handled by the try/except below, same as pre-existing
        # duplicate rows always were.
        "DROP INDEX IF EXISTS ix_domain_bucket_domain",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_domain_bucket_domain "
        "ON domain_minute_aggregates (bucket_ts, domain, branch)",
        "DROP INDEX IF EXISTS ix_client_bucket_ip_user_unique",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_client_bucket_ip_user_unique "
        'ON client_minute_aggregates (bucket_ts, client_ip, branch, COALESCE("user", \'\'))',
        "DROP INDEX IF EXISTS ix_client_hourly_bucket_ip_user_unique",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_client_hourly_bucket_ip_user_unique "
        'ON client_hourly_aggregates (bucket_ts, client_ip, branch, COALESCE("user", \'\'))',
        "DROP INDEX IF EXISTS ix_client_category_bucket_ip_category",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_client_category_bucket_ip_category "
        "ON client_category_minute_aggregates (bucket_ts, client_ip, category, branch)",
        "DROP INDEX IF EXISTS ix_minute_aggregates_bucket_ts",
        "CREATE INDEX IF NOT EXISTS ix_minute_aggregates_bucket_ts ON minute_aggregates (bucket_ts)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_minute_bucket_branch "
        "ON minute_aggregates (bucket_ts, branch)",
    ]
    for statement in statements:
        try:
            async with bind_engine.begin() as conn:
                await conn.execute(text(statement))
        except DBAPIError:
            # Pre-existing duplicate rows (from before this constraint
            # existed) would make index creation fail -- log and continue
            # rather than blocking startup over a defensive integrity
            # constraint.
            logger.warning(
                "Could not run aggregate-table DDL statement %r; there may "
                "be pre-existing duplicate rows to clean up",
                statement,
                exc_info=True,
            )


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
