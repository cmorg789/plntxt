from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.memory import (
    MemoryCategory,
    MemoryPostRelationship,
    MemoryRelationship,
)


class MemoryCreate(BaseModel):
    category: MemoryCategory
    content: str
    tags: list[str] | None = None
    expires_at: datetime | None = None
    public: bool | None = None


class MemoryUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    expires_at: datetime | None = None
    public: bool | None = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: MemoryCategory
    content: str
    tags: list[str] | None
    public: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    next_cursor: str | None


class MemoryLinkCreate(BaseModel):
    source_id: UUID
    target_id: UUID
    relationship: MemoryRelationship


class MemoryLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    target_id: UUID
    relationship_type: MemoryRelationship


class MemoryPostLinkCreate(BaseModel):
    memory_id: UUID
    post_id: UUID
    relationship: MemoryPostRelationship


class MemoryPostLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memory_id: UUID
    post_id: UUID
    relationship_type: MemoryPostRelationship
