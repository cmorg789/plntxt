import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        return uuid.UUID(sub)
    except (JWTError, ValueError):
        return None
