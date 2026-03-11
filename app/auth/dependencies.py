
from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.config import settings
from app.db import get_db
from app.models.session import Session
from app.models.user import User, UserRole


async def _get_user_from_token(
    token: str, db: AsyncSession
) -> User | None:
    user_id = decode_access_token(token)
    if user_id is None:
        return None

    # Verify the session exists and hasn't expired
    result = await db.execute(
        select(Session).where(Session.token == token)
    )
    session = result.scalar_one_or_none()
    # Compare as naive UTC — DB stores naive datetimes
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if session is None or session.expires_at < now_utc:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.is_banned:
        return None
    return user


async def get_optional_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
    session_token: str | None = Cookie(None),
) -> User | None:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif session_token:
        token = session_token
    if token is None:
        return None
    return await _get_user_from_token(token, db)


async def get_current_user(
    user: User | None = Depends(get_optional_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def _get_agent_by_api_key(
    x_api_key: str | None, db: AsyncSession
) -> User | None:
    if not x_api_key:
        return None
    # Check per-user API keys first
    result = await db.execute(
        select(User).where(User.api_key == x_api_key, User.role == UserRole.AGENT)
    )
    user = result.scalar_one_or_none()
    if user:
        return user
    # Fall back to global key
    if x_api_key == settings.AGENT_API_KEY:
        result = await db.execute(
            select(User).where(User.role == UserRole.AGENT).limit(1)
        )
        return result.scalar_one_or_none()
    return None


async def get_agent_user(
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    user: User | None = Depends(get_optional_user),
) -> User:
    agent = await _get_agent_by_api_key(x_api_key, db)
    if agent:
        return agent
    if user and user.role == UserRole.AGENT:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access required")


async def get_agent_or_admin(
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    user: User | None = Depends(get_optional_user),
) -> User:
    agent = await _get_agent_by_api_key(x_api_key, db)
    if agent:
        return agent
    if user and user.role in (UserRole.AGENT, UserRole.ADMIN):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent or admin access required")


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
