"""Issue a dev JWT directly against the DB — bypassing Google OAuth.

Useful while you're still setting up Google Cloud credentials but want to
exercise the frontend against the API. If the user doesn't exist, creates
them as ADMIN + is_active=True.

Usage:
    poetry run python scripts/issue_dev_token.py admin@example.com

The script prints localStorage snippets you can paste into the browser
devtools console on the Polaris web app to simulate a logged-in session.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.security import create_access_token, create_refresh_token
from app.db.session import AsyncSessionLocal
from app.models.token import Token
from app.models.user import User, UserRole


async def main(email: str) -> None:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                name=email.split("@", 1)[0],
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            created = True
        else:
            created = False

        access = create_access_token(user_id=user.id, subject=user.email)
        refresh = create_refresh_token(user_id=user.id, subject=user.email)
        db.add(Token(refresh_token=refresh, user_id=user.id, is_active=True))
        await db.commit()
        await db.refresh(user)

    print(f"user_id={user.id} email={user.email} role={user.role.value} "
          f"({'created' if created else 'existing'})")
    print("\naccess_token:", access)
    print("refresh_token:", refresh)
    print("\nPaste into the Polaris web app devtools console "
          "(sessions live in cookies now so proxy.ts can see them):")
    access_maxage = 30 * 60
    refresh_maxage = 7 * 24 * 60 * 60
    user_json = (
        f'{{id:{user.id},email:"{user.email}",name:"{user.name}",'
        f'role:"{user.role.value}",is_active:true}}'
    )
    print(
        f'  document.cookie = "polaris.access={access}; '
        f'Max-Age={access_maxage}; Path=/; SameSite=Lax"'
    )
    print(
        f'  document.cookie = "polaris.refresh={refresh}; '
        f'Max-Age={refresh_maxage}; Path=/; SameSite=Lax"'
    )
    print(
        f'  document.cookie = "polaris.user=" + encodeURIComponent(JSON.stringify('
        f'{user_json})) + "; Max-Age={refresh_maxage}; Path=/; SameSite=Lax"'
    )
    print("  location.href = '/dashboard'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: poetry run python scripts/issue_dev_token.py <email>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
