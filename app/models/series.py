import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Series(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "series"

    title: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    posts: Mapped[list["Post"]] = relationship(  # noqa: F821
        back_populates="series",
        order_by="Post.series_position",
    )
