from fastapi import APIRouter, Depends, HTTPException, Response, status
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_agent_or_admin
from app.db import get_db
from app.models.post import Post, PostStatus
from app.models.series import Series
from app.models.schemas.series import (
    SeriesAssignPost,
    SeriesCreate,
    SeriesDetailResponse,
    SeriesListResponse,
    SeriesPostItem,
    SeriesResponse,
    SeriesUpdate,
)
from app.models.user import User

router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=SeriesListResponse)
async def list_series(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Series).order_by(Series.created_at.desc())
    )
    items = result.scalars().all()
    return SeriesListResponse(
        items=[SeriesResponse.model_validate(s) for s in items],
    )


@router.get("/{slug}", response_model=SeriesDetailResponse)
async def get_series(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Series)
        .where(Series.slug == slug)
        .options(selectinload(Series.posts))
    )
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    published_posts = sorted(
        [p for p in series.posts if p.status == PostStatus.PUBLISHED],
        key=lambda p: (p.series_position is None, p.series_position),
    )

    return SeriesDetailResponse(
        **SeriesResponse.model_validate(series).model_dump(),
        posts=[
            SeriesPostItem(
                slug=p.slug,
                title=p.title,
                position=p.series_position,
                published_at=p.published_at,
            )
            for p in published_posts
        ],
    )


@router.post("", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
async def create_series(
    data: SeriesCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    slug = slugify(data.title)

    existing = await db.execute(select(Series).where(Series.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A series with this slug already exists")

    series = Series(
        title=data.title,
        slug=slug,
        description=data.description,
    )
    db.add(series)
    await db.commit()
    await db.refresh(series)
    return SeriesResponse.model_validate(series)


@router.patch("/{slug}", response_model=SeriesResponse)
async def update_series(
    slug: str,
    data: SeriesUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    result = await db.execute(select(Series).where(Series.slug == slug))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(series, field, value)

    await db.commit()
    await db.refresh(series)
    return SeriesResponse.model_validate(series)


@router.post("/{slug}/posts", response_model=SeriesResponse)
async def assign_post_to_series(
    slug: str,
    data: SeriesAssignPost,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    result = await db.execute(select(Series).where(Series.slug == slug))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    result = await db.execute(select(Post).where(Post.slug == data.post_slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    post.series_id = series.id
    post.series_position = data.position

    await db.commit()
    await db.refresh(series)
    return SeriesResponse.model_validate(series)


@router.delete("/{slug}/posts/{post_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_post_from_series(
    slug: str,
    post_slug: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    result = await db.execute(select(Series).where(Series.slug == slug))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    result = await db.execute(select(Post).where(Post.slug == post_slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    post.series_id = None
    post.series_position = None

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
