from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.post import PostStatus


class PostCreate(BaseModel):
    title: str
    body: str
    tags: list[str] | None = None
    status: PostStatus = PostStatus.DRAFT


class PostUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: PostStatus | None = None


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    body: str
    tags: list[str] | None
    status: PostStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class PostListResponse(BaseModel):
    items: list[PostResponse]
    next_cursor: str | None
