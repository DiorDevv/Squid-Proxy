import pytest
from pydantic import ValidationError

from app.core.config import (
    INSECURE_DEFAULT_ADMIN_PASSWORD,
    INSECURE_DEFAULT_JWT_SECRET,
    INSECURE_DEFAULT_POSTGRES_PASSWORD,
    Settings,
)

_REAL_JWT_SECRET = "a-real-random-secret-at-least-32-characters-long"
# Production refuses a SQLite DATABASE_URL (see the SQLite tests below), so
# every "in production, ..." test that isn't about the DB URL itself has to
# pass a real Postgres one to reach the check it's actually exercising.
_PG_URL = "postgresql+asyncpg://squid:a-real-password@postgres:5432/squid_dashboard"


def test_production_rejects_insecure_default_jwt_secret():
    with pytest.raises(ValidationError, match="insecure default"):
        Settings(ENVIRONMENT="production", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET, DATABASE_URL=_PG_URL)


def test_production_accepts_a_real_jwt_secret():
    settings = Settings(ENVIRONMENT="production", JWT_SECRET=_REAL_JWT_SECRET, DATABASE_URL=_PG_URL)
    assert settings.JWT_SECRET == _REAL_JWT_SECRET


def test_production_rejects_a_too_short_jwt_secret():
    with pytest.raises(ValidationError, match="shorter than 32"):
        Settings(ENVIRONMENT="production", JWT_SECRET="short-but-not-the-default", DATABASE_URL=_PG_URL)


def test_production_rejects_wildcard_cors_origin():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=_REAL_JWT_SECRET,
            DATABASE_URL=_PG_URL,
            CORS_ORIGINS=["*"],
        )


def test_development_allows_a_short_jwt_secret_and_wildcard_cors():
    settings = Settings(ENVIRONMENT="development", JWT_SECRET="short", CORS_ORIGINS=["*"])
    assert settings.CORS_ORIGINS == ["*"]


def test_development_allows_the_insecure_default_jwt_secret():
    settings = Settings(ENVIRONMENT="development", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET)
    assert settings.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET


def test_production_rejects_the_env_example_admin_password_placeholder():
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=_REAL_JWT_SECRET,
            ADMIN_PASSWORD=INSECURE_DEFAULT_ADMIN_PASSWORD,
            DATABASE_URL=_PG_URL,
        )


def test_production_accepts_a_real_admin_password():
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=_REAL_JWT_SECRET,
        ADMIN_PASSWORD="a-real-password",
        DATABASE_URL=_PG_URL,
    )
    assert settings.ADMIN_PASSWORD == "a-real-password"


def test_development_allows_the_admin_password_placeholder():
    settings = Settings(ENVIRONMENT="development", ADMIN_PASSWORD=INSECURE_DEFAULT_ADMIN_PASSWORD)
    assert settings.ADMIN_PASSWORD == INSECURE_DEFAULT_ADMIN_PASSWORD


def test_production_rejects_the_default_postgres_password_in_database_url():
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=_REAL_JWT_SECRET,
            DATABASE_URL=f"postgresql+asyncpg://squid:{INSECURE_DEFAULT_POSTGRES_PASSWORD}@postgres:5432/squid_dashboard",
        )


def test_production_accepts_a_real_postgres_password_in_database_url():
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=_REAL_JWT_SECRET,
        DATABASE_URL="postgresql+asyncpg://squid:a-real-password@postgres:5432/squid_dashboard",
    )
    assert INSECURE_DEFAULT_POSTGRES_PASSWORD not in settings.DATABASE_URL


def test_production_rejects_a_sqlite_database_url():
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=_REAL_JWT_SECRET,
            ADMIN_PASSWORD="a-real-password",
            DATABASE_URL="sqlite+aiosqlite:///./squid_dashboard.db",
        )


def test_production_allows_sqlite_with_the_explicit_escape_hatch():
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=_REAL_JWT_SECRET,
        ADMIN_PASSWORD="a-real-password",
        DATABASE_URL="sqlite+aiosqlite:///./squid_dashboard.db",
        ALLOW_SQLITE_IN_PRODUCTION=True,
    )
    assert settings.DATABASE_URL.startswith("sqlite")


def test_development_allows_sqlite_by_default():
    settings = Settings(ENVIRONMENT="development", DATABASE_URL="sqlite+aiosqlite:///./x.db")
    assert settings.DATABASE_URL.startswith("sqlite")
