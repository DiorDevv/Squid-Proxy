"""Rate limiting setup (brute-force protection on auth endpoints)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
