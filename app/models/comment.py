import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AuthorType(str, enum.Enum):
    HUMAN = "human"
    AI = "ai"


class CommentStatus(str, enum.Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    SHADOWED = "shadowed"
    FLAGGED = "flagged"


class ResponseStatus(str, enum.Enum):
    PENDING = "pending"
    NEEDS_RESPONSE = "needs_response"
    SKIP = "skip"
    RESPONDED = "responded"


class Comment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    author_type: Mapped[AuthorType] = mapped_column(default=AuthorType.HUMAN)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CommentStatus] = mapped_column(default=CommentStatus.VISIBLE)
    response_status: Mapped[ResponseStatus] = mapped_column(default=ResponseStatus.PENDING)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    post: Mapped["Post"] = relationship(back_populates="comments")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="comments")  # noqa: F821
    parent: Mapped["Comment | None"] = relationship(
        remote_side="Comment.id", back_populates="replies"
    )
    replies: Mapped[list["Comment"]] = relationship(back_populates="parent")
