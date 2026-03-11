import enum

from sqlalchemy import String, Text
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

    comments: Mapped[list["Comment"]] = relationship(back_populates="post")  # noqa: F821
    media: Mapped[list["Media"]] = relationship(back_populates="post")  # noqa: F821
    memory_links: Mapped[list["MemoryPostLink"]] = relationship(back_populates="post")  # noqa: F821
