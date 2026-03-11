import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base, TimestampMixin, UUIDMixin


class MemoryCategory(str, enum.Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class MemoryRelationship(str, enum.Enum):
    ELABORATES = "elaborates"
    CONTRADICTS = "contradicts"
    FOLLOWS_FROM = "follows_from"
    INSPIRED_BY = "inspired_by"


class MemoryPostRelationship(str, enum.Enum):
    INSPIRED_BY = "inspired_by"
    REFERENCED_IN = "referenced_in"
    FOLLOW_UP_TO = "follow_up_to"


class Memory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "memory"

    category: Mapped[MemoryCategory]
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    expires_at: Mapped[datetime | None]
    public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    embedding = mapped_column(Vector(256), nullable=True)

    source_links: Mapped[list["MemoryLink"]] = relationship(
        foreign_keys="MemoryLink.source_id", back_populates="source"
    )
    target_links: Mapped[list["MemoryLink"]] = relationship(
        foreign_keys="MemoryLink.target_id", back_populates="target"
    )
    post_links: Mapped[list["MemoryPostLink"]] = relationship(back_populates="memory")


class MemoryLink(UUIDMixin, Base):
    __tablename__ = "memory_links"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory.id", ondelete="CASCADE")
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory.id", ondelete="CASCADE")
    )
    relationship_type: Mapped[MemoryRelationship] = mapped_column(
        name="relationship"
    )

    source: Mapped[Memory] = relationship(foreign_keys=[source_id], back_populates="source_links")
    target: Mapped[Memory] = relationship(foreign_keys=[target_id], back_populates="target_links")


class MemoryPostLink(UUIDMixin, Base):
    __tablename__ = "memory_post_links"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory.id", ondelete="CASCADE")
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE")
    )
    relationship_type: Mapped[MemoryPostRelationship] = mapped_column(
        name="relationship"
    )

    memory: Mapped[Memory] = relationship(back_populates="post_links")
    post: Mapped["Post"] = relationship(back_populates="memory_links")  # noqa: F821
