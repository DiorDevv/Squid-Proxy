from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.models import db as db_module
from app.models.db import _build_engine_kwargs


def _memory_engine():
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


async def test_init_db_builds_schema_when_not_alembic_managed(monkeypatch):
    engine = _memory_engine()
    monkeypatch.setattr(db_module, "engine", engine)
    try:
        await db_module.init_db()
        names = await _table_names(engine)
        assert "raw_events" in names
        # create_all built the schema; it never creates alembic_version.
        assert "alembic_version" not in names
    finally:
        await engine.dispose()


async def test_init_db_skips_create_all_when_alembic_version_present(monkeypatch):
    """Once a DB is Alembic-managed, init_db() must not also run create_all --
    that second authority is exactly what could mask a missing migration."""
    engine = _memory_engine()
    monkeypatch.setattr(db_module, "engine", engine)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32) NOT NULL)"))
        await db_module.init_db()
        assert await _table_names(engine) == {"alembic_version"}
    finally:
        await engine.dispose()


def test_sqlite_url_gets_no_pool_kwargs():
    settings = Settings(DATABASE_URL="sqlite+aiosqlite:///./squid_dashboard.db")
    kwargs = _build_engine_kwargs(settings)
    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs
    assert kwargs["pool_pre_ping"] is True


def test_postgres_url_gets_configured_pool_kwargs():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard",
        DATABASE_POOL_SIZE=10,
        DATABASE_MAX_OVERFLOW=20,
    )
    kwargs = _build_engine_kwargs(settings)
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20


def test_postgres_url_defaults_match_sqlalchemy_library_defaults():
    settings = Settings(DATABASE_URL="postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard")
    kwargs = _build_engine_kwargs(settings)
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 10
