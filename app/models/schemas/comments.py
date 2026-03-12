from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.comment import AuthorType, CommentStatus, ResponseStatus


class CommentCreate(BaseModel):
    body: str


class CommentUpdate(BaseModel):
    status: CommentStatus | None = None
    response_status: ResponseStatus | None = None
    is_moderated: bool | None = None
    is_replied: bool | None = None
    reason: str | None = None


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    parent_id: uuid.UUID | None
    user_id: uuid.UUID
    author_type: AuthorType
    body: str
    status: CommentStatus
    response_status: ResponseStatus
    is_moderated: bool
    is_replied: bool
    created_at: datetime
    author_username: str
    author_avatar: str | None


class CommentTreeResponse(CommentResponse):
    replies: list[CommentTreeResponse] = []


class PendingCommentsResponse(BaseModel):
    items: list[CommentResponse]
    next_cursor: str | None
