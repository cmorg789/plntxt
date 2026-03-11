from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from slugify import slugify
from sqlalchemy import Text, case, cast, func, literal, or_, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user, get_agent_or_admin, get_optional_user
from app.db import get_db
from app.models.comment import Comment, CommentStatus
from app.models.post import Post, PostStatus
from app.models.revision import PostRevision
from app.pagination import decode_cursor, encode_cursor
from app.models.schemas.posts import PostCreate, PostListResponse, PostResponse, PostUpdate, PostRevisionListResponse, PostRevisionResponse, PostEngagementItem, EngagementSummaryResponse
from app.models.user import User, UserRole

router = APIRouter(prefix="/posts", tags=["posts"])



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
        cursor_ts, cursor_id = decode_cursor(cursor)
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
        ts = posts[-1].published_at if use_published and posts[-1].published_at else posts[-1].created_at
        next_cursor = encode_cursor(ts, posts[-1].id)

    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in posts],
        next_cursor=next_cursor,
    )


@router.get("/search", response_model=PostListResponse)
async def search_posts(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    like_pattern = f"%{q}%"
    title_sim = func.similarity(Post.title, q)
    body_sim = func.similarity(Post.body, q)
    stmt = (
        select(Post)
        .where(
            Post.status == PostStatus.PUBLISHED,
            or_(
                title_sim > 0.1,
                body_sim > 0.1,
                Post.title.ilike(like_pattern),
                Post.body.ilike(like_pattern),
            ),
        )
        .order_by((title_sim + body_sim).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    posts = list(result.scalars().all())
    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in posts],
        next_cursor=None,
    )


@router.get("/engagement", response_model=EngagementSummaryResponse)
async def get_engagement_summary(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    stmt = (
        select(
            Post,
            func.count(Comment.id).label("comment_count"),
            func.count(case((Comment.created_at >= week_ago, Comment.id))).label("comment_count_recent"),
        )
        .outerjoin(Comment, (Comment.post_id == Post.id) & (Comment.status == CommentStatus.VISIBLE))
        .where(Post.status == PostStatus.PUBLISHED)
        .group_by(Post.id)
        .order_by(Post.view_count.desc(), func.count(Comment.id).desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    total_views = await db.scalar(select(func.sum(Post.view_count)).select_from(Post)) or 0

    return EngagementSummaryResponse(
        posts=[
            PostEngagementItem(
                id=row.Post.id,
                title=row.Post.title,
                slug=row.Post.slug,
                view_count=row.Post.view_count,
                comment_count=row.comment_count,
                comment_count_recent=row.comment_count_recent,
                published_at=row.Post.published_at,
            )
            for row in rows
        ],
        total_views=total_views,
        generated_at=now,
    )


@router.get("/{slug}/revisions", response_model=PostRevisionListResponse)
async def list_post_revisions(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Post not found")

    revs = await db.execute(
        select(PostRevision)
        .where(PostRevision.post_id == post.id)
        .order_by(PostRevision.revision_number.desc())
    )
    return PostRevisionListResponse(
        items=[PostRevisionResponse.model_validate(r) for r in revs.scalars().all()]
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

    published_at = datetime.utcnow() if data.status == PostStatus.PUBLISHED else None

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

    # Snapshot current state before applying changes
    if "body" in update_data or "title" in update_data:
        rev_count = await db.scalar(
            select(func.count()).select_from(PostRevision).where(PostRevision.post_id == post.id)
        )
        db.add(PostRevision(
            post_id=post.id,
            revision_number=(rev_count or 0) + 1,
            title=post.title,
            body=post.body,
        ))

    for field, value in update_data.items():
        setattr(post, field, value)

    # Set published_at when transitioning to PUBLISHED for the first time
    if post.status == PostStatus.PUBLISHED and post.published_at is None:
        post.published_at = datetime.utcnow()

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
