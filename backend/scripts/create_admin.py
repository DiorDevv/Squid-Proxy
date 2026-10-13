#!/usr/bin/env python3
"""CLI to create a user or reset an existing user's password. Run from the
backend/ dir. The usual way to get the first super admin onto a fresh
install (or back into one where every super admin is locked out); everyone
else is normally created from Settings -> Users.

Usage:
    python scripts/create_admin.py --username ops --role superadmin
    (prompts for the password interactively; use --password only for
    scripted/non-interactive runs, e.g. CI -- it's visible to other local
    users via `ps`/`/proc/<pid>/cmdline` and lands in shell history)

The password must meet the same policy as one set in the dashboard (see
app/core/password_policy.py). An existing user given here is also
re-activated and has its role updated.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.password_policy import normalize_username, password_problems, username_problem  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.db import AsyncSessionLocal, init_db  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


async def create_or_update_user(username: str, password: str, role: str, full_name: str) -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if existing:
            existing.hashed_password = hash_password(password)
            existing.role = UserRole(role)
            existing.is_active = True
            existing.must_change_password = False
            if existing.role == UserRole.SUPERADMIN:
                existing.branch = None
            # Every session of the account ends -- same as a reset in the UI.
            existing.token_version += 1
            print(f"Updated existing user {username} (role={role})")
        else:
            session.add(
                User(
                    username=username,
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=UserRole(role),
                )
            )
            print(f"Created user {username} (role={role})")
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", default="")
    parser.add_argument(
        "--password",
        help="Non-interactive password (scripted/CI use only -- omit to be prompted instead).",
    )
    parser.add_argument("--role", choices=[r.value for r in UserRole], default="superadmin")
    args = parser.parse_args()

    username = normalize_username(args.username)
    if problem := username_problem(username):
        sys.exit(problem)
    password = args.password or getpass.getpass("Password: ")
    if problems := password_problems(password, username):
        sys.exit("Password does not meet the requirements: " + "; ".join(problems))
    asyncio.run(create_or_update_user(username, password, args.role, args.full_name))


if __name__ == "__main__":
    main()
