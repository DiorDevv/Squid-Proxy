import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class TotpRecoveryCode(Base):
    """One-time-use fallback codes issued when TOTP is confirmed (see
    app/services/totp_service.py.confirm_setup) -- lets an admin who's lost
    their authenticator device still get in, rather than being permanently
    locked out with no path back except direct DB access. Only the hash is
    ever stored (same as passwords/refresh tokens); the plaintext codes are
    shown to the admin exactly once, at confirmation time, and never
    retrievable again."""

    __tablename__ = "totp_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # None until consumed -- a used code is kept (not deleted) so
    # verify_login_code can reject a replay of an already-spent code
    # instead of a second successful login from the same one-time code.
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
