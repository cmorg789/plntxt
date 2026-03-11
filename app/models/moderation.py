import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin


class ModerationAction(str, enum.Enum):
    HIDE = "hide"
    SHADOW = "shadow"
    FLAG = "flag"
    BAN = "ban"


class RuleType(str, enum.Enum):
    KEYWORD = "keyword"
    PATTERN = "pattern"
    THRESHOLD = "threshold"


class ModerationLog(UUIDMixin, Base):
    __tablename__ = "moderation_log"

    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    action: Mapped[ModerationAction]
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    comment: Mapped["Comment"] = relationship()  # noqa: F821


class ModerationRule(UUIDMixin, Base):
    __tablename__ = "moderation_rules"

    rule_type: Mapped[RuleType]
    value: Mapped[str] = mapped_column(String(500))
    action: Mapped[ModerationAction]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Ban(UUIDMixin, Base):
    __tablename__ = "bans"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime | None]

    user: Mapped["User"] = relationship(back_populates="bans")  # noqa: F821
