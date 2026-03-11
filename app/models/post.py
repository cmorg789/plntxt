import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

from datetime import datetime


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Post(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "posts"

    title: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    status: Mapped[PostStatus] = mapped_column(default=PostStatus.DRAFT)
    published_at: Mapped[datetime | None]
    view_count: Mapped[int] = mapped_column(default=0, server_default="0")
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    series_position: Mapped[int | None] = mapped_column(Integer)

    series: Mapped["Series | None"] = relationship(back_populates="posts")  # noqa: F821
    revisions: Mapped[list["PostRevision"]] = relationship(back_populates="post", order_by="PostRevision.revision_number.desc()")  # noqa: F821
    comments: Mapped[list["Comment"]] = relationship(back_populates="post")  # noqa: F821
    media: Mapped[list["Media"]] = relationship(back_populates="post")  # noqa: F821
    memory_links: Mapped[list["MemoryPostLink"]] = relationship(back_populates="post")  # noqa: F821
