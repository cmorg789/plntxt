import enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    AGENT = "agent"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_banned: Mapped[bool] = mapped_column(default=False)

    comments: Mapped[list["Comment"]] = relationship(back_populates="user")  # noqa: F821
    sessions: Mapped[list["Session"]] = relationship(back_populates="user")  # noqa: F821
    bans: Mapped[list["Ban"]] = relationship(back_populates="user")  # noqa: F821
