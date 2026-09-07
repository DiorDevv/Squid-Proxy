"""Unit tests for app/core/security.py's JWT handling -- in particular the
JWT_SECRET rotation grace window (verify against the previous secret too)
and the kid header. Integration-level auth flows live in test_auth.py.
"""

import jwt
import pytest

from app.core import security
from app.core.config import Settings

_CUR = "current-secret-current-secret-0123456789"
_OLD = "previous-secret-previous-secret-0123456789"


def _use_settings(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: Settings(**overrides))


def test_token_minted_with_current_secret_decodes(monkeypatch):
    _use_settings(monkeypatch, JWT_SECRET=_CUR)
    token = security.create_access_token("u1", "admin")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["role"] == "admin"


def test_kid_header_is_present_and_stable(monkeypatch):
    _use_settings(monkeypatch, JWT_SECRET=_CUR)
    token = security.create_access_token("u1", "admin")
    kid = jwt.get_unverified_header(token)["kid"]
    assert kid and kid == security._kid(_CUR)
    # Different secret -> different kid, and it never contains the secret.
    assert security._kid(_OLD) != kid
    assert _CUR not in kid and _OLD not in security._kid(_OLD)


def test_token_from_previous_secret_still_verifies_during_grace_window(monkeypatch):
    # Minted before the rotation...
    _use_settings(monkeypatch, JWT_SECRET=_OLD)
    old_token = security.create_access_token("u1", "viewer")
    # ...rotation lands: new signing secret, old one kept as PREVIOUS.
    _use_settings(monkeypatch, JWT_SECRET=_CUR, JWT_SECRET_PREVIOUS=_OLD)
    payload = security.decode_access_token(old_token)
    assert payload["sub"] == "u1"


def test_token_from_old_secret_rejected_once_previous_is_cleared(monkeypatch):
    _use_settings(monkeypatch, JWT_SECRET=_OLD)
    old_token = security.create_access_token("u1", "viewer")
    _use_settings(monkeypatch, JWT_SECRET=_CUR)  # no PREVIOUS -> grace window over
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(old_token)


def test_non_access_token_is_rejected(monkeypatch):
    _use_settings(monkeypatch, JWT_SECRET=_CUR)
    refreshy = jwt.encode({"sub": "u1", "type": "refresh"}, _CUR, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError, match="Not an access token"):
        security.decode_access_token(refreshy)


def test_garbage_token_raises_invalid_token_error(monkeypatch):
    _use_settings(monkeypatch, JWT_SECRET=_CUR)
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token("not.a.jwt")
