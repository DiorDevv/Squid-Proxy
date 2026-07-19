import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_DEFAULT_JWT_SECRET, Settings


def test_production_rejects_insecure_default_jwt_secret():
    with pytest.raises(ValidationError, match="insecure default"):
        Settings(ENVIRONMENT="production", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET)


def test_production_accepts_a_real_jwt_secret():
    settings = Settings(ENVIRONMENT="production", JWT_SECRET="a-real-random-secret")
    assert settings.JWT_SECRET == "a-real-random-secret"


def test_development_allows_the_insecure_default_jwt_secret():
    settings = Settings(ENVIRONMENT="development", JWT_SECRET=INSECURE_DEFAULT_JWT_SECRET)
    assert settings.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET
