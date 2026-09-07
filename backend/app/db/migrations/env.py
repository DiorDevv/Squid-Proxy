import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.types import TypeEngine

# Importing the package registers every model's table on Base.metadata --
# the single canonical list lives in app/models/__init__.py so autogenerate
# and `alembic check` see the whole schema, not a subset that silently
# drifts from what actually ships.
import app.models  # noqa: F401,E402
from app.core.config import get_settings
from app.models.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# raw_events.bytes / .duration_ms are BigInteger in the model, but migration
# c1e7a4b9d2f6 only ALTERs them on Postgres -- SQLite's INTEGER storage
# class is already 64-bit, so the migration is a deliberate no-op there.
# That leaves the *reflected* SQLite type as INTEGER while the model says
# BigInteger, which `alembic check` would otherwise flag as drift forever.
# Suppress exactly that one comparison on SQLite (and nothing else).
_SQLITE_BIGINT_NOOP_COLUMNS = {"bytes", "duration_ms"}


def _compare_type(
    context_: MigrationContext,
    inspected_column: Column[Any],
    metadata_column: Column[Any],
    inspected_type: TypeEngine[Any],
    metadata_type: TypeEngine[Any],
) -> bool | None:
    if (
        context_.dialect.name == "sqlite"
        and metadata_column.table.name == "raw_events"
        and metadata_column.name in _SQLITE_BIGINT_NOOP_COLUMNS
        and inspected_type.__class__.__name__ == "INTEGER"
        and metadata_type.__class__.__name__ == "BigInteger"
    ):
        return False  # not a real change on SQLite -- see comment above
    return None  # fall back to Alembic's default type comparison


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=_compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=_compare_type
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
