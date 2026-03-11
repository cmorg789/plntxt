from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user, get_agent_or_admin, get_optional_user
from app.db import get_db
from app.models.post import Post, PostStatus
from app.models.schemas.posts import PostCreate, PostListResponse, PostResponse, PostUpdate
from app.models.user import User, UserRole

router = APIRouter(prefix="/posts", tags=["posts"])


def _parse_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Parse a cursor string of the form '{created_at_iso}_{id}'."""
    sep = cursor.rfind("_")
    if sep == -1:
        raise HTTPException(status_code=400, detail="Invalid cursor format")
    ts_part = cursor[:sep]
    id_part = cursor[sep + 1 :]
    try:
        ts = datetime.fromisoformat(ts_part)
        uid = UUID(id_part)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor format") from exc
    return ts, uid


def _build_cursor(post: Post, *, use_published: bool) -> str:
    """Build a cursor string from a post."""
    ts = post.published_at if use_published and post.published_at else post.created_at
    return f"{ts.isoformat()}_{post.id}"


@router.get("", response_model=PostListResponse)
async def list_posts(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    is_privileged = user is not None and user.role in (UserRole.AGENT, UserRole.ADMIN)

    stmt = select(Post)

    # Status filtering
    if status_filter:
        try:
            requested_status = PostStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")
        if requested_status != PostStatus.PUBLISHED and not is_privileged:
            raise HTTPException(status_code=403, detail="Cannot view non-published posts")
        stmt = stmt.where(Post.status == requested_status)
    elif not is_privileged:
        stmt = stmt.where(Post.status == PostStatus.PUBLISHED)

    # Tag filtering
    if tag:
        stmt = stmt.where(Post.tags.any(tag))

    # Determine sort column: published posts sort by published_at, otherwise created_at
    use_published = not status_filter or status_filter == PostStatus.PUBLISHED.value
    sort_col = Post.published_at if use_published else Post.created_at

    # Cursor-based pagination
    if cursor:
        cursor_ts, cursor_id = _parse_cursor(cursor)
        stmt = stmt.where(
            (sort_col < cursor_ts)
            | ((sort_col == cursor_ts) & (Post.id < cursor_id))
        )

    stmt = stmt.order_by(sort_col.desc(), Post.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    posts = list(result.scalars().all())

    next_cursor: str | None = None
    if len(posts) > limit:
        posts = posts[:limit]
        next_cursor = _build_cursor(posts[-1], use_published=use_published)

    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in posts],
        next_cursor=next_cursor,
    )


@router.get("/{slug}", response_model=PostResponse)
async def get_post(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    is_privileged = user is not None and user.role in (UserRole.AGENT, UserRole.ADMIN)
    if post.status != PostStatus.PUBLISHED and not is_privileged:
        raise HTTPException(status_code=404, detail="Post not found")

    return PostResponse.model_validate(post)


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    data: PostCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    slug = slugify(data.title)

    # Ensure slug uniqueness
    existing = await db.execute(select(Post).where(Post.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A post with this slug already exists")

    published_at = datetime.now(timezone.utc) if data.status == PostStatus.PUBLISHED else None

    post = Post(
        title=data.title,
        slug=slug,
        body=data.body,
        tags=data.tags,
        status=data.status,
        published_at=published_at,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return PostResponse.model_validate(post)


@router.patch("/{slug}", response_model=PostResponse)
async def update_post(
    slug: str,
    data: PostUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(post, field, value)

    # Set published_at when transitioning to PUBLISHED for the first time
    if post.status == PostStatus.PUBLISHED and post.published_at is None:
        post.published_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(post)
    return PostResponse.model_validate(post)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    await db.delete(post)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
