import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin


class Session(UUIDMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")

    user: Mapped["User"] = relationship(back_populates="sessions")  # noqa: F821
