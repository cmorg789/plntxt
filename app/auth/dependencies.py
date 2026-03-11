
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.config import settings
from app.db import get_db
from app.models.user import User, UserRole


async def _get_user_from_token(
    token: str, db: AsyncSession
) -> User | None:
    user_id = decode_access_token(token)
    if user_id is None:
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


async def get_agent_user(
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    user: User | None = Depends(get_optional_user),
) -> User:
    # API key auth for agent
    if x_api_key and x_api_key == settings.AGENT_API_KEY:
        result = await db.execute(select(User).where(User.role == UserRole.AGENT))
        agent = result.scalar_one_or_none()
        if agent:
            return agent
    # Fall back to JWT auth
    if user and user.role == UserRole.AGENT:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access required")


async def get_agent_or_admin(
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    user: User | None = Depends(get_optional_user),
) -> User:
    # API key auth for agent
    if x_api_key and x_api_key == settings.AGENT_API_KEY:
        result = await db.execute(select(User).where(User.role == UserRole.AGENT))
        agent = result.scalar_one_or_none()
        if agent:
            return agent
    # JWT auth for agent or admin
    if user and user.role in (UserRole.AGENT, UserRole.ADMIN):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent or admin access required")


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
