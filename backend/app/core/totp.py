"""TOTP (RFC 6238, on top of HOTP/RFC 4226) for admin two-factor login.

Implemented against the stdlib (hmac/hashlib/base64/secrets) rather than
adding a dependency -- the algorithm is short and fully specified, and this
keeps the same "no heavy/unnecessary dependency" posture as the rest of
this project (see e.g. category_inference.py's UT1 blacklist handling).
Compatible with every standard authenticator app (Google Authenticator,
Authy, 1Password, ...): 30-second step, SHA-1, 6 digits -- the universal
defaults every app assumes when an otpauth:// URI doesn't say otherwise.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_STEP_SECONDS = 30
_DIGITS = 6
_SECRET_BYTES = 20  # 160 bits -- RFC 4226's own recommended HOTP key length


def generate_secret() -> str:
    """A fresh base32 secret, unpadded (matches how every authenticator app
    displays/expects it for manual entry)."""
    return base64.b32encode(secrets.token_bytes(_SECRET_BYTES)).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    # Base32 requires padding back to a multiple of 8 chars to decode --
    # generate_secret() strips it for display, so restore it here.
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10**_DIGITS)).zfill(_DIGITS)


def current_code(secret: str, for_time: float | None = None) -> str:
    t = time.time() if for_time is None else for_time
    return _hotp(secret, int(t // _STEP_SECONDS))


def verify_code(secret: str, code: str, valid_window: int = 1, for_time: float | None = None) -> bool:
    """Accepts a code from the current 30s step or up to `valid_window`
    steps on either side, to tolerate ordinary clock drift between the
    server and the phone running the authenticator app -- not a
    brute-force-friendliness tradeoff, since the caller (totp_service.py)
    is responsible for rate-limiting attempts, not this function.
    """
    if not code.isdigit() or len(code) != _DIGITS:
        return False
    t = time.time() if for_time is None else for_time
    counter = int(t // _STEP_SECONDS)
    # Constant-time comparison per candidate so a timing side-channel can't
    # narrow down which of the ~3 accepted codes (if any) is closest to a
    # match -- matches this codebase's existing verify_refresh_secret
    # pattern (secrets.compare_digest) rather than `==`.
    return any(
        secrets.compare_digest(_hotp(secret, counter + offset), code)
        for offset in range(-valid_window, valid_window + 1)
    )


def provisioning_uri(secret: str, email: str, issuer: str = "Squid Watch") -> str:
    """otpauth:// URI an authenticator app can scan (as a QR code, rendered
    client-side) or import directly -- RFC unofficial but universally
    supported de facto standard (Google Authenticator's key URI format)."""
    label = quote(f"{issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={_DIGITS}&period={_STEP_SECONDS}"
    )


def generate_recovery_codes(count: int = 10) -> list[str]:
    """One-time-use fallback codes for when the authenticator device is
    lost -- shown once at TOTP setup time (see totp_service.confirm_setup),
    never retrievable again after that (only their hashes are stored, same
    as passwords/refresh tokens -- see app/models/totp_recovery_code.py).
    Formatted in two groups of 5 (xxxxx-xxxxx) purely for readability when
    an admin has to type one in by hand."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/O/1/l/i -- avoids transcription errors
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes
