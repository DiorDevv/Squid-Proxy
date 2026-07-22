import pytest
from pydantic import ValidationError

from app.core.config import (
    INSECURE_DEFAULT_ADMIN_PASSWORD,
    INSECURE_DEFAULT_JWT_SECRET,
    INSECURE_DEFAULT_POSTGRES_PASSWORD,
    Settings,
)

_REAL_JWT_SECRET = "a-real-random-secret"


def test_production_rejects_insecure_default_jwt_secret():
    with pytest.raises(ValidationError, match="insecure default"):
        Settings(ENVIRONMENT="production", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET)


def test_production_accepts_a_real_jwt_secret():
    settings = Settings(ENVIRONMENT="production", JWT_SECRET="a-real-random-secret")
    assert settings.JWT_SECRET == "a-real-random-secret"


def test_development_allows_the_insecure_default_jwt_secret():
    settings = Settings(ENVIRONMENT="development", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET)
    assert settings.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET


def test_production_rejects_the_env_example_admin_password_placeholder():
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=_REAL_JWT_SECRET,
            ADMIN_PASSWORD=INSECURE_DEFAULT_ADMIN_PASSWORD,
        )


def test_production_accepts_a_real_admin_password():
    settings = Settings(
        ENVIRONMENT="production", JWT_SECRET=_REAL_JWT_SECRET, ADMIN_PASSWORD="a-real-password"
    )
    assert settings.ADMIN_PASSWORD == "a-real-password"


def test_development_allows_the_admin_password_placeholder():
    settings = Settings(
        ENVIRONMENT="development", ADMIN_PASSWORD=INSECURE_DEFAULT_ADMIN_PASSWORD
    )
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
