"""Async SQLAlchemy engine/session setup.

Driver is selected purely from the `DATABASE_URL` scheme, so switching from
the SQLite default to Postgres is a one-line env var change with no code
changes (see ARCHITECTURE.md).
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_settings = get_settings()


def _build_engine_kwargs(settings: Settings) -> dict:
    """kwargs for create_async_engine, split out as a pure function so pool
    sizing can be unit-tested without opening a real connection (see
    tests/test_db.py). pool_size/max_overflow are only meaningful for a
    real connection-pooled DBAPI (Postgres); sqlite's single local file
    gets no benefit from a bigger pool, and passing these kwargs through to
    aiosqlite's pool class isn't something worth depending on, so they're
    only added for non-sqlite URLs."""
    kwargs: dict = dict(
        echo=False,
        future=True,
        # A pooled connection that's gone stale (Postgres restarted, a
        # NAT/load-balancer idle-timeout silently dropped it) would
        # otherwise surface as a request-killing error on whichever caller
        # happens to check it out next -- pre_ping runs a cheap liveness
        # check before handing a pooled connection back out and
        # transparently reconnects if it's dead, instead of letting a
        # stale connection fail a real request.
        pool_pre_ping=True,
    )
    if not settings.DATABASE_URL.startswith("sqlite"):
        kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
        kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
    return kwargs


engine = create_async_engine(_settings.DATABASE_URL, **_build_engine_kwargs(_settings))

if _settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(
        dbapi_connection: DBAPIConnection, connection_record: ConnectionPoolEntry
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


def _has_alembic_version(sync_conn: Connection) -> bool:
    return inspect(sync_conn).has_table("alembic_version")


async def init_db() -> None:
    # Importing the package registers every model on Base.metadata -- one
    # canonical list, see app/models/__init__.py.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        alembic_managed = await conn.run_sync(_has_alembic_version)

    if alembic_managed:
        # This database is under Alembic (docker-entrypoint.sh / the systemd
        # unit both run `alembic upgrade head` before the app starts). Alembic
        # is then the sole schema authority -- running create_all here too
        # would be a silent second authority that could paper over a missing
        # migration. CI's `alembic check` is what guards drift now.
        logger.info("Schema is Alembic-managed; skipping create_all")
        return

    # No alembic_version table: a fresh dev database started with a bare
    # `uvicorn app.main:app` and no migration step. Build it straight from
    # the models so that path still needs zero setup.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Deliberately outside the create_all transaction: each statement below
    # runs in its own connection/transaction so a failure on one (or on a
    # database with pre-existing duplicate rows) can't poison the others or
    # roll back the schema that create_all just committed.
    await _ensure_aggregate_unique_indexes(engine)


async def _ensure_aggregate_unique_indexes(bind_engine: AsyncEngine | None = None) -> None:
    """Idempotently add the aggregate-table unique indexes on the
    `create_all` path only -- a real deployment gets these from the Alembic
    chain instead (verified: `alembic upgrade head` produces every index
    listed below), and init_db() no longer calls this once a database is
    Alembic-managed. See migration 466aaa85c9f3_aggregate_unique_constraints
    for the rationale. `create_all` alone won't add these to a table that
    already exists, and the expression-based client index can't be declared
    in the ORM model at all, so both are applied here as plain idempotent
    DDL.

    Still reached on two non-Alembic paths: a bare `uvicorn app.main:app`
    dev database, and tests (conftest.py's db_engine fixture passes its own
    in-memory engine), so the ON CONFLICT target app/services/db_upsert.py
    relies on for client_minute_aggregates exists there too.
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
