from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SeriesCreate(BaseModel):
    title: str
    description: str | None = None


class SeriesUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class SeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class SeriesDetailResponse(SeriesResponse):
    """Series with its ordered posts — used on series detail page."""
    posts: list["SeriesPostItem"]


class SeriesPostItem(BaseModel):
    """Minimal post info for series listing."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    series_position: int | None
    published_at: datetime | None


class SeriesListResponse(BaseModel):
    items: list[SeriesResponse]


class SeriesAssignPost(BaseModel):
    post_slug: str
    position: int
