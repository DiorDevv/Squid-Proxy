"""Username and password rules for locally managed accounts.

The frontend mirrors these rules for live hints (see
frontend/src/lib/password-policy.ts), but the server is the authority --
every password set through the API goes through check_password here.
"""

import re
import secrets

MIN_LENGTH = 12
MAX_LENGTH = 128
# A user changing their own password may not reuse their current password
# or any of the previous HISTORY - 1 (see user_service.change_own_password).
HISTORY = 5

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
RESERVED_USERNAMES = frozenset({"anonymous", "system", "root", "unknown", "tizim"})

_COMMON = (
    "password",
    "parol",
    "qwerty",
    "123456",
    "111111",
    "abc123",
    "letmein",
    "welcome",
    "iloveyou",
    "admin123",
    "p@ssw0rd",
    "squid",
)

# No look-alike characters (0/O, 1/l/I) -- a temporary password is read off
# a screen and typed by hand.
_GENERATED_GROUPS = ("abcdefghijkmnpqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789", "-_!@#%+=?")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def username_problem(username: str) -> str | None:
    """None if `username` (already normalized) is an acceptable login name."""
    if not USERNAME_RE.match(username):
        return (
            "Username must be 3-64 characters: lowercase latin letters, digits, '.', '_' or '-', "
            "starting with a letter or digit."
        )
    if username in RESERVED_USERNAMES:
        return "This username is reserved."
    return None


def password_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"at most {MAX_LENGTH} characters")
    classes = sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )
    if classes < 3:
        problems.append("at least 3 of: lowercase, uppercase, digit, symbol")
    lowered = password.lower()
    if len(username) >= 3 and username.lower() in lowered:
        problems.append("must not contain the username")
    if any(word in lowered for word in _COMMON):
        problems.append("must not contain a common word or sequence (e.g. 'password', '123456')")
    if password and len(set(password)) < 6:
        problems.append("at least 6 different characters")
    return problems


def generate_password(length: int = 16) -> str:
    alphabet = "".join(_GENERATED_GROUPS)
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if all(any(c in group for c in candidate) for group in _GENERATED_GROUPS) and not password_problems(
            candidate
        ):
            return candidate
