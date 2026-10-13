"""First-boot convenience: create an initial super admin if no user exists."""

import logging

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.password_policy import normalize_username
from app.core.security import hash_password
from app.models.db import AsyncSessionLocal
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


def bootstrap_username() -> str | None:
    """ADMIN_USERNAME, or -- for .env files written before username login --
    the part of ADMIN_EMAIL before the "@"."""
    settings = get_settings()
    if settings.ADMIN_USERNAME:
        return normalize_username(settings.ADMIN_USERNAME)
    if settings.ADMIN_EMAIL:
        return normalize_username(settings.ADMIN_EMAIL.split("@", 1)[0])
    return None


async def bootstrap_admin_user() -> None:
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if user_count > 0:
            return

        username = bootstrap_username()
        if not username or not settings.ADMIN_PASSWORD:
            logger.warning(
                "No users exist and ADMIN_USERNAME/ADMIN_PASSWORD are not set; "
                "use scripts/create_admin.py to create the first super admin."
            )
            return

        admin = User(
            username=username,
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.SUPERADMIN,
        )
        session.add(admin)
        await session.commit()
        logger.info("Bootstrapped initial super admin", extra={"username": username})
