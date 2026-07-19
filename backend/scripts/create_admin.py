#!/usr/bin/env python3
"""CLI to create/update a user (admin or viewer). Run from the backend/ dir.

Usage:
    python scripts/create_admin.py --email ops@company.com --password '...' --role admin
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


async def create_or_update_user(email: str, password: str, role: str) -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            existing.hashed_password = hash_password(password)
            existing.role = UserRole(role)
            print(f"Updated existing user {email} (role={role})")
        else:
            session.add(User(email=email, hashed_password=hash_password(password), role=UserRole(role)))
            print(f"Created user {email} (role={role})")
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", choices=["admin", "viewer"], default="viewer")
    args = parser.parse_args()

    asyncio.run(create_or_update_user(args.email, args.password, args.role))


if __name__ == "__main__":
    main()
