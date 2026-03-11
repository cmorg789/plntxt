from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.post import PostStatus


class PostCreate(BaseModel):
    title: str
    body: str
    tags: list[str] | None = None
    status: PostStatus = PostStatus.DRAFT
    series_id: UUID | None = None


class PostUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: PostStatus | None = None
    series_id: UUID | None = None


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
    view_count: int = 0
    series_id: UUID | None = None
    series_position: int | None = None


class PostListResponse(BaseModel):
    items: list[PostResponse]
    next_cursor: str | None


class PostRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    post_id: UUID
    revision_number: int
    title: str
    body: str
    created_at: datetime


class PostRevisionListResponse(BaseModel):
    items: list[PostRevisionResponse]


class PostEngagementItem(BaseModel):
    id: UUID
    title: str
    slug: str
    view_count: int
    comment_count: int
    comment_count_recent: int
    published_at: datetime | None


class EngagementSummaryResponse(BaseModel):
    posts: list[PostEngagementItem]
    total_views: int
    generated_at: datetime
