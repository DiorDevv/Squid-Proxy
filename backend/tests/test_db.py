from app.core.config import Settings
from app.models.db import _build_engine_kwargs


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
