"""Password hashing, JWT access tokens, opaque refresh tokens, and WS tickets."""

import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"

# A precomputed bcrypt hash of a random value, with no matching plaintext.
# Used to run a real bcrypt verify for nonexistent users so login's response
# time doesn't reveal whether an email is registered (timing side-channel).
_DUMMY_HASH = pwd_context.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    """Verify a password, running bcrypt even when `hashed` is None.

    Callers with no matching user row should pass `hashed=None` rather than
    short-circuiting before calling this function, so failed logins for a
    nonexistent email take the same time as a wrong-password login for a
    real one.
    """
    return pwd_context.verify(password, hashed if hashed is not None else _DUMMY_HASH) and hashed is not None


def create_access_token(user_id: str, role: str, branch: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "branch": branch,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise JWTError("Not an access token")
    return payload


def generate_refresh_secret() -> tuple[str, str, str, datetime]:
    """Returns (jti, raw_secret, secret_hash, expires_at) for a new refresh token."""
    settings = get_settings()
    jti = str(uuid.uuid4())
    raw_secret = secrets.token_urlsafe(32)
    secret_hash = hash_refresh_secret(raw_secret)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jti, raw_secret, secret_hash, expires_at


def hash_refresh_secret(raw_secret: str) -> str:
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def verify_refresh_secret(raw_secret: str, secret_hash: str) -> bool:
    return secrets.compare_digest(hash_refresh_secret(raw_secret), secret_hash)


def encode_refresh_cookie_value(jti: str, raw_secret: str) -> str:
    return f"{jti}.{raw_secret}"


def decode_refresh_cookie_value(value: str) -> tuple[str, str] | None:
    if "." not in value:
        return None
    jti, _, raw_secret = value.partition(".")
    if not jti or not raw_secret:
        return None
    return jti, raw_secret


class WsTicketStore:
    """In-memory single-use tickets for authenticating the /ws/live handshake.

    Browsers cannot set custom headers on a WebSocket handshake, so a
    short-lived, single-use ticket (obtained via a normal authenticated REST
    call) is passed as a query param instead of the real access token --
    keeping the long-lived JWT out of URLs and server access logs.

    Single-process, in-memory by design (matches the ring buffer's scaling
    envelope); a multi-instance deployment would need a shared store.
    """

    def __init__(self, ttl_seconds: float = 30.0, sweep_every: int = 100) -> None:
        self.ttl_seconds = ttl_seconds
        self._sweep_every = sweep_every
        self._issued_since_sweep = 0
        self._tickets: dict[str, tuple[str, str, str | None, float]] = {}

    def issue(self, user_id: str, role: str, branch: str | None = None) -> str:
        self._issued_since_sweep += 1
        if self._issued_since_sweep >= self._sweep_every:
            self._sweep_expired()
        ticket = secrets.token_urlsafe(24)
        self._tickets[ticket] = (user_id, role, branch, time.monotonic() + self.ttl_seconds)
        return ticket

    def consume(self, ticket: str) -> tuple[str, str, str | None] | None:
        entry = self._tickets.pop(ticket, None)
        if entry is None:
            return None
        user_id, role, branch, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return user_id, role, branch

    def _sweep_expired(self) -> None:
        """Drop tickets that were issued but never consumed before expiring.

        Runs periodically (every `sweep_every` issued tickets) rather than on
        every issue, since a client that always redeems its ticket never
        needs a sweep -- this only matters for abandoned/never-redeemed ones.
        """
        self._issued_since_sweep = 0
        now = time.monotonic()
        expired = [key for key, (_, _, _, expires_at) in self._tickets.items() if now > expires_at]
        for key in expired:
            del self._tickets[key]
