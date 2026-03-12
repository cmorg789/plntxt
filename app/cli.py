"""CLI utilities for plntxt.

Usage:
    python -m app.cli create-admin --email admin@example.com --username admin
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db import async_session
from app.models.user import User, UserRole


async def _create_admin(username: str, email: str, password: str) -> None:
    async with async_session() as session:
        existing = await session.execute(
            select(User).where((User.username == username) | (User.email == email))
        )
        if existing.scalar_one_or_none():
            print(f"Error: user with username '{username}' or email '{email}' already exists.")
            sys.exit(1)

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin user '{username}' created.")


def main():
    parser = argparse.ArgumentParser(prog="plntxt", description="plntxt CLI utilities")
    sub = parser.add_subparsers(dest="command")

    admin_parser = sub.add_parser("create-admin", help="Create an admin user")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--email", required=True)

    args = parser.parse_args()

    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: password cannot be empty.")
            sys.exit(1)
        asyncio.run(_create_admin(args.username, args.email, password))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
