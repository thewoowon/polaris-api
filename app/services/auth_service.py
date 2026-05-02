"""Google OAuth (operator login) + JWT issuance.

Flow:
1. Frontend sends user to GET /auth/google/login → backend 302s to Google.
2. Google redirects back to GOOGLE_REDIRECT_URI (a frontend page) with ?code=.
3. Frontend POSTs {code} to /auth/google/callback → this module exchanges,
   verifies, upserts the User, issues (access, refresh).

Blueprint §19: prefer explicit over clever. No session, no magic; every
auto-created user produces an audit trail via the callers.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.token import Token
from app.models.user import User, UserRole

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class AuthError(Exception):
    """Raised on any OAuth / domain / token verification failure."""


def build_google_auth_url() -> str:
    if not settings.GOOGLE_CLIENT_ID:
        raise AuthError("GOOGLE_CLIENT_ID not configured")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _allowed_domains() -> list[str]:
    raw = settings.GOOGLE_ALLOWED_DOMAINS or ""
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def domain_allowed(email: str) -> bool:
    domains = _allowed_domains()
    if not domains:
        return True
    domain = email.lower().rsplit("@", 1)[-1]
    return domain in domains


async def _exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as http:
        res = await http.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    if res.status_code != 200:
        raise AuthError(f"Google token exchange failed: {res.status_code} {res.text[:200]}")
    return res.json()


async def _verify_id_token(id_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as http:
        res = await http.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
    if res.status_code != 200:
        raise AuthError(f"Google tokeninfo failed: {res.status_code} {res.text[:200]}")
    info = res.json()
    if info.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise AuthError("id_token audience mismatch")
    if info.get("email_verified") not in (True, "true"):
        raise AuthError("email not verified by Google")
    return info


async def login_with_google(
    db: AsyncSession, *, code: str
) -> tuple[User, str, str]:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise AuthError("Google OAuth not configured")

    token_payload = await _exchange_code(code)
    id_token = token_payload.get("id_token")
    if not id_token:
        raise AuthError("Google response missing id_token")

    info = await _verify_id_token(id_token)
    email = (info.get("email") or "").strip()
    if not email:
        raise AuthError("Google response missing email")

    if not domain_allowed(email):
        raise AuthError(f"domain not allowed: {email.rsplit('@', 1)[-1]}")

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None:
        # First user becomes ADMIN; subsequent new users default to REVIEWER.
        existing = (await db.execute(select(func.count()).select_from(User))).scalar_one() or 0
        role = UserRole.ADMIN if existing == 0 else UserRole.REVIEWER
        user = User(
            email=email,
            name=info.get("name") or email.split("@", 1)[0],
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    elif not user.is_active:
        raise AuthError("user is deactivated")

    access = create_access_token(user_id=user.id, subject=user.email)
    refresh = create_refresh_token(user_id=user.id, subject=user.email)

    db.add(Token(refresh_token=refresh, user_id=user.id, is_active=True))
    await db.commit()
    await db.refresh(user)
    return user, access, refresh


async def refresh_access(db: AsyncSession, *, refresh_token: str) -> tuple[User, str, str]:
    payload = decode_token(refresh_token)  # raises 401 on failure
    if payload.get("typ") != "refresh":
        raise AuthError("not a refresh token")

    user_id = payload.get("user_id")
    if user_id is None:
        raise AuthError("refresh token missing user_id")

    token_row = (
        await db.execute(
            select(Token).where(
                Token.refresh_token == refresh_token,
                Token.user_id == user_id,
                Token.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if token_row is None:
        raise AuthError("refresh token revoked or unknown")

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("user not found or deactivated")

    new_access = create_access_token(user_id=user.id, subject=user.email)
    new_refresh = create_refresh_token(user_id=user.id, subject=user.email)

    # Rotate: invalidate old row, insert new.
    token_row.is_active = False
    db.add(Token(refresh_token=new_refresh, user_id=user.id, is_active=True))
    await db.commit()
    return user, new_access, new_refresh


async def logout_user(db: AsyncSession, *, user_id: int) -> int:
    rows = (
        await db.execute(
            select(Token).where(Token.user_id == user_id, Token.is_active.is_(True))
        )
    ).scalars().all()
    for t in rows:
        t.is_active = False
    await db.commit()
    return len(rows)
