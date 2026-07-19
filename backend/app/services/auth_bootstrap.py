"""First-boot convenience: create an initial admin user if none exists."""

import logging

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.db import AsyncSessionLocal
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def bootstrap_admin_user() -> None:
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if user_count > 0:
            return

        if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
            logger.warning(
                "No users exist and ADMIN_EMAIL/ADMIN_PASSWORD are not set; "
                "use scripts/create_admin.py to create the first user."
            )
            return

        admin = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.commit()
        logger.info("Bootstrapped initial admin user", extra={"email": settings.ADMIN_EMAIL})
