"""TOTP two-factor setup/confirm/disable and login-time code verification.

Setup is two steps on purpose (begin_setup, then confirm_setup) rather than
enabling on secret generation alone: an admin who scans the QR but never
successfully enters a code (closed the tab, app showed a different code
than expected, ...) must not end up with an account silently "protected"
by a secret they never actually confirmed works -- see User.totp_secret's
own docstring.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.totp import (
    generate_recovery_codes,
    generate_secret,
    provisioning_uri,
)
from app.core.totp import (
    verify_code as verify_totp_code,
)
from app.models.audit_log import AuditAction
from app.models.totp_recovery_code import TotpRecoveryCode
from app.models.user import User
from app.services import audit_service

TOTP_NOT_PENDING = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="No TOTP setup in progress -- call setup again first.",
)
TOTP_ALREADY_ENABLED = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is already enabled."
)
INVALID_TOTP_CODE = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code.")
TOTP_NOT_ENABLED = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled."
)
INVALID_PASSWORD = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password."
)

_ISSUER = "Squid Watch"


def begin_setup(user: User) -> tuple[str, str]:
    """Generates a new secret and stashes it on the (already-loaded) user
    object -- caller commits. Returns (secret, otpauth_uri) for the
    frontend to render as a QR code / show as manually-enterable text.
    Re-callable before confirm_setup (e.g. the admin re-opens the dialog):
    each call replaces the still-unconfirmed secret, never appends."""
    if user.totp_enabled:
        raise TOTP_ALREADY_ENABLED
    secret = generate_secret()
    user.totp_secret = secret
    return secret, provisioning_uri(secret, user.email, issuer=_ISSUER)


async def confirm_setup(session: AsyncSession, user: User, code: str, actor_user_id: str) -> list[str]:
    """Verifies the just-scanned code against the pending secret from
    begin_setup, and only then flips totp_enabled on. Also mints this
    account's recovery codes -- shown to the admin exactly once in the
    response, only their bcrypt hashes are ever persisted."""
    if user.totp_enabled:
        raise TOTP_ALREADY_ENABLED
    if not user.totp_secret:
        raise TOTP_NOT_PENDING
    if not verify_totp_code(user.totp_secret, code):
        raise INVALID_TOTP_CODE

    user.totp_enabled = True
    codes = generate_recovery_codes()
    session.add_all(
        [TotpRecoveryCode(user_id=user.id, code_hash=hash_password(raw_code)) for raw_code in codes]
    )
    await audit_service.record(
        session,
        action=AuditAction.TOTP_ENABLED,
        actor_user_id=actor_user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.email,
    )
    await session.commit()
    return codes


async def disable(session: AsyncSession, user: User, password: str, actor_user_id: str) -> None:
    """Requires the current password (not just an active session) so a
    hijacked-but-not-yet-detected session can't silently turn 2FA off for
    itself -- the same "prove you're still really you" bar this project
    already applies to nothing else destructive enough to warrant it until
    now (contrast update_role/delete_user, which trust the session alone)."""
    if not user.totp_enabled:
        raise TOTP_NOT_ENABLED
    if not verify_password(password, user.hashed_password):
        raise INVALID_PASSWORD

    user.totp_secret = None
    user.totp_enabled = False
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user.id))
    await audit_service.record(
        session,
        action=AuditAction.TOTP_DISABLED,
        actor_user_id=actor_user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.email,
    )
    await session.commit()


async def verify_login_code(session: AsyncSession, user: User, code: str) -> bool:
    """Tries the code as a TOTP first, then as an unused recovery code --
    a recovery code is consumed (marked used, never valid again) the
    moment it's accepted, whether or not the caller goes on to actually
    complete the login."""
    if not user.totp_secret:
        return False
    if verify_totp_code(user.totp_secret, code):
        return True

    unused_codes = (
        await session.execute(
            select(TotpRecoveryCode).where(
                TotpRecoveryCode.user_id == user.id, TotpRecoveryCode.used_at.is_(None)
            )
        )
    ).scalars().all()
    for row in unused_codes:
        if verify_password(code, row.code_hash):
            await session.execute(
                update(TotpRecoveryCode)
                .where(TotpRecoveryCode.id == row.id)
                .values(used_at=datetime.now(UTC))
            )
            await audit_service.record(
                session,
                action=AuditAction.TOTP_RECOVERY_CODE_USED,
                actor_user_id=user.id,
                branch=user.branch,
                target_user_id=user.id,
                target_email=user.email,
            )
            await session.commit()
            return True
    return False
