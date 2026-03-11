"""Shared session construction and cookie helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import Response

from app.config import settings
from app.models.session import Session


def build_session(user_id: uuid.UUID, token: str) -> Session:
    return Session(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow()
        + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
