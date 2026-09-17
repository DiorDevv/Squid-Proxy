"""Password hashing, JWT access tokens, opaque refresh tokens, and WS tickets."""

import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings

ACCESS_TOKEN_TYPE = "access"


def _kid(secret: str) -> str:
    """A short, stable, non-reversible label for which signing secret an
    access token was made with -- put in the JWT header so an operator (or
    this code, as a decode hint) can tell a token minted before a
    JWT_SECRET rotation from one minted after. Domain-separated so it's not
    a bare hash of the secret."""
    return hashlib.sha256(b"squidwatch-jwt-kid|" + secret.encode("utf-8")).hexdigest()[:12]


def _verification_secrets() -> list[str]:
    """Secrets a token is allowed to verify against: the live JWT_SECRET
    first, then JWT_SECRET_PREVIOUS if set (and different). Setting the old
    value as JWT_SECRET_PREVIOUS for one access-token lifetime after a
    rotation lets already-issued tokens keep working instead of every
    session breaking the instant the secret changes."""
    settings = get_settings()
    secrets_ = [settings.JWT_SECRET]
    prev = settings.JWT_SECRET_PREVIOUS
    if prev and prev != settings.JWT_SECRET:
        secrets_.append(prev)
    return secrets_


def _bcrypt_bytes(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes of input and raises on longer
    # input as of 4.1 (older versions silently truncated) -- truncate
    # ourselves so behavior is consistent across versions.
    return password.encode("utf-8")[:72]


def _gensalt() -> bytes:
    # Work factor comes from settings (default 12) purely so the test suite
    # can drop it to 4 -- see Settings.BCRYPT_ROUNDS. A wrong-but-lower
    # value here only weakens hashing, it can't break verification: bcrypt
    # encodes the cost in the hash string itself, so checkpw() against an
    # existing 12-round hash still works after this changes.
    return bcrypt.gensalt(rounds=get_settings().BCRYPT_ROUNDS)


# A precomputed bcrypt hash of a random value, with no matching plaintext.
# Used to run a real bcrypt verify for nonexistent users so login's response
# time doesn't reveal whether an email is registered (timing side-channel).
_DUMMY_HASH = bcrypt.hashpw(_bcrypt_bytes(secrets.token_urlsafe(32)), _gensalt()).decode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), _gensalt()).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    """Verify a password, running bcrypt even when `hashed` is None.

    Callers with no matching user row should pass `hashed=None` rather than
    short-circuiting before calling this function, so failed logins for a
    nonexistent email take the same time as a wrong-password login for a
    real one.
    """
    target = hashed if hashed is not None else _DUMMY_HASH
    return bcrypt.checkpw(_bcrypt_bytes(password), target.encode("ascii")) and hashed is not None


def create_access_token(
    user_id: str, role: str, branch: str | None = None, token_version: int | None = None
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "branch": branch,
        # The account's token_version at mint time -- get_current_user
        # rejects the token once the live row's value moves past this (a
        # role/branch change or password reset bumps it). Omitted only by
        # callers that predate the column; a token with no "tv" is
        # grandfathered there rather than rejected outright.
        "tv": token_version,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": _kid(settings.JWT_SECRET)},
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode + verify an access token. Raises jwt.InvalidTokenError on a bad
    signature, an expired token, a malformed token, or a token that isn't an
    access token. Tries the live secret first, then JWT_SECRET_PREVIOUS
    (see _verification_secrets) so a secret rotation doesn't invalidate
    still-valid tokens all at once."""
    settings = get_settings()
    candidates = _verification_secrets()

    # If the token's kid matches one of our secrets, verify against just
    # that one; otherwise fall back to trying each. A wrong/absent kid is
    # only a hint, never trusted -- the signature check is what decides.
    try:
        token_kid = jwt.get_unverified_header(token).get("kid")
    except InvalidTokenError:
        token_kid = None
    if token_kid:
        matched = [s for s in candidates if _kid(s) == token_kid]
        if matched:
            candidates = matched

    last_error: InvalidTokenError | None = None
    for secret in candidates:
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
            break
        except InvalidTokenError as exc:  # bad signature for this secret, or expired, or malformed
            last_error = exc
    else:
        raise last_error or InvalidTokenError("Could not decode token")

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("Not an access token")
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
        # ticket -> (user_id, role, branch, token_version, expires_at)
        self._tickets: dict[str, tuple[str, str, str | None, int | None, float]] = {}

    def issue(
        self, user_id: str, role: str, branch: str | None = None, token_version: int | None = None
    ) -> str:
        self._issued_since_sweep += 1
        if self._issued_since_sweep >= self._sweep_every:
            self._sweep_expired()
        ticket = secrets.token_urlsafe(24)
        self._tickets[ticket] = (
            user_id,
            role,
            branch,
            token_version,
            time.monotonic() + self.ttl_seconds,
        )
        return ticket

    def consume(self, ticket: str) -> tuple[str, str, str | None, int | None] | None:
        entry = self._tickets.pop(ticket, None)
        if entry is None:
            return None
        user_id, role, branch, token_version, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return user_id, role, branch, token_version

    def _sweep_expired(self) -> None:
        """Drop tickets that were issued but never consumed before expiring.

        Runs periodically (every `sweep_every` issued tickets) rather than on
        every issue, since a client that always redeems its ticket never
        needs a sweep -- this only matters for abandoned/never-redeemed ones.
        """
        self._issued_since_sweep = 0
        now = time.monotonic()
        expired = [key for key, entry in self._tickets.items() if now > entry[-1]]
        for key in expired:
            del self._tickets[key]


class MfaChallengeStore:
    """In-memory single-use challenges bridging login's two steps for a
    TOTP-enabled account: password verified but the code not yet entered.
    Deliberately not a JWT -- unlike an access/refresh token this must be
    revocable server-side after a fixed number of wrong-code guesses
    (a 6-digit TOTP code is brute-forceable given enough attempts, so the
    challenge itself -- not just the login route's own rate limit -- needs
    to die after a handful of failures rather than staying guessable for
    its whole TTL). Same single-process, in-memory scope as WsTicketStore.
    """

    MAX_ATTEMPTS = 5

    def __init__(self, ttl_seconds: float = 300.0, sweep_every: int = 100) -> None:
        self.ttl_seconds = ttl_seconds
        self._sweep_every = sweep_every
        self._issued_since_sweep = 0
        # token -> (user_id, expires_at, attempts_so_far)
        self._challenges: dict[str, tuple[str, float, int]] = {}

    def issue(self, user_id: str) -> str:
        self._issued_since_sweep += 1
        if self._issued_since_sweep >= self._sweep_every:
            self._sweep_expired()
        token = secrets.token_urlsafe(24)
        self._challenges[token] = (user_id, time.monotonic() + self.ttl_seconds, 0)
        return token

    def peek(self, token: str) -> str | None:
        """The challenge's user_id without consuming it or counting an
        attempt -- callers must still call either consume() (on a correct
        code) or record_failure() (on a wrong one) to move the challenge
        forward."""
        entry = self._challenges.get(token)
        if entry is None:
            return None
        user_id, expires_at, _attempts = entry
        if time.monotonic() > expires_at:
            del self._challenges[token]
            return None
        return user_id

    def record_failure(self, token: str) -> None:
        """Counts one wrong-code attempt; invalidates the whole challenge
        once MAX_ATTEMPTS is reached, forcing a fresh login+password rather
        than leaving a guessable challenge alive for its full TTL."""
        entry = self._challenges.get(token)
        if entry is None:
            return
        user_id, expires_at, attempts = entry
        attempts += 1
        if attempts >= self.MAX_ATTEMPTS:
            del self._challenges[token]
        else:
            self._challenges[token] = (user_id, expires_at, attempts)

    def consume(self, token: str) -> str | None:
        """Call only once the code has been verified correct -- single-use,
        same as WsTicketStore.consume."""
        user_id = self.peek(token)
        if user_id is None:
            return None
        del self._challenges[token]
        return user_id

    def _sweep_expired(self) -> None:
        self._issued_since_sweep = 0
        now = time.monotonic()
        expired = [key for key, (_, expires_at, _) in self._challenges.items() if now > expires_at]
        for key in expired:
            del self._challenges[key]


class LoginThrottle:
    """Per-account brute-force throttle, layered on top of the per-IP rate
    limit (app/core/rate_limit.py) -- which a distributed attacker (a
    botnet, an IPv6 /64) sidesteps by spreading guesses across source IPs
    while still hammering one account.

    After `failure_threshold` failed logins for one email within
    `failure_window_seconds`, that email is "throttled": at most one further
    attempt is allowed per `throttled_interval_seconds`, regardless of
    source IP, until it goes a full `failure_window_seconds` with no new
    failure. There is no hard lock -- a correct password is still accepted
    on the next allowed attempt and clears the record immediately -- so an
    attacker who merely knows an email address cannot lock its owner out.

    The login route makes a blocked attempt indistinguishable from an
    ordinary wrong password (same 401, same bcrypt time), so tripping this
    is invisible to the caller.

    Single-process/in-memory by design, same envelope as WsTicketStore.
    """

    def __init__(
        self,
        failure_threshold: int = 10,
        failure_window_seconds: float = 900.0,
        throttled_interval_seconds: float = 60.0,
        sweep_every: int = 200,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.throttled_interval_seconds = throttled_interval_seconds
        self._sweep_every = sweep_every
        self._checks_since_sweep = 0
        # email -> (recent failure monotonic timestamps, last real-attempt ts)
        self._entries: dict[str, tuple[list[float], float]] = {}

    @staticmethod
    def key(email: str) -> str:
        return email.strip().lower()

    def _recent_failures(self, email: str, now: float) -> list[float]:
        entry = self._entries.get(email)
        if entry is None:
            return []
        return [t for t in entry[0] if now - t < self.failure_window_seconds]

    def allow_attempt(self, email: str) -> bool:
        """True if a login attempt for `email` should be processed now.
        Pure check -- the route still calls record_failure/record_success
        for attempts it actually processed."""
        self._checks_since_sweep += 1
        if self._checks_since_sweep >= self._sweep_every:
            self._sweep()
        now = time.monotonic()
        failures = self._recent_failures(email, now)
        if len(failures) < self.failure_threshold:
            return True
        last_attempt_at = self._entries[email][1]
        return now - last_attempt_at >= self.throttled_interval_seconds

    def record_failure(self, email: str) -> None:
        now = time.monotonic()
        failures = self._recent_failures(email, now)
        failures.append(now)
        self._entries[email] = (failures, now)

    def record_success(self, email: str) -> None:
        self._entries.pop(email, None)

    def _sweep(self) -> None:
        self._checks_since_sweep = 0
        now = time.monotonic()
        stale = [
            email
            for email, (failures, last_attempt_at) in self._entries.items()
            if not any(now - t < self.failure_window_seconds for t in failures)
            and now - last_attempt_at >= self.failure_window_seconds
        ]
        for email in stale:
            del self._entries[email]
