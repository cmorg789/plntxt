from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import (
    get_admin_user,
    get_agent_or_admin,
    get_agent_user,
    get_current_user,
)
from app.db import get_db
from app.models.comment import AuthorType, Comment, CommentStatus, ResponseStatus
from app.pagination import decode_cursor, encode_cursor
from app.models.post import Post
from app.models.schemas.comments import (
    CommentCreate,
    CommentResponse,
    CommentTreeResponse,
    CommentUpdate,
    PendingCommentsResponse,
)
from app.models.user import User, UserRole

router = APIRouter(tags=["comments"])

DEFAULT_PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comment_to_response(comment: Comment) -> CommentResponse:
    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        user_id=comment.user_id,
        author_type=comment.author_type,
        body=comment.body,
        status=comment.status,
        response_status=comment.response_status,
        created_at=comment.created_at,
        author_username=comment.user.username,
        author_avatar=comment.user.avatar_url,
    )


def _comment_to_tree(comment: Comment) -> CommentTreeResponse:
    visible_replies = [
        r for r in (comment.replies or []) if r.status == CommentStatus.VISIBLE
    ]
    return CommentTreeResponse(
        id=comment.id,
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        user_id=comment.user_id,
        author_type=comment.author_type,
        body=comment.body,
        status=comment.status,
        response_status=comment.response_status,
        created_at=comment.created_at,
        author_username=comment.user.username,
        author_avatar=comment.user.avatar_url,
        replies=[_comment_to_tree(r) for r in visible_replies],
    )



async def _get_post_by_slug(slug: str, db: AsyncSession) -> Post:
    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/posts/{slug}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    slug: str,
    body: CommentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    post = await _get_post_by_slug(slug, db)

    author_type = AuthorType.AI if user.role == UserRole.AGENT else AuthorType.HUMAN
    comment = Comment(
        post_id=post.id,
        user_id=user.id,
        author_type=author_type,
        body=body.body,
        ip_address=request.client.host if request.client else None,
    )
    db.add(comment)
    await db.flush()

    # Attach user for response building
    comment.user = user
    await db.commit()

    return _comment_to_response(comment)


@router.post("/comments/{comment_id}/reply", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def reply_to_comment(
    comment_id: uuid.UUID,
    body: CommentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    author_type = AuthorType.AI if user.role == UserRole.AGENT else AuthorType.HUMAN
    reply = Comment(
        post_id=parent.post_id,
        parent_id=parent.id,
        user_id=user.id,
        author_type=author_type,
        body=body.body,
        ip_address=request.client.host if request.client else None,
    )
    db.add(reply)
    await db.flush()

    reply.user = user
    await db.commit()

    return _comment_to_response(reply)


@router.get("/posts/{slug}/comments", response_model=list[CommentTreeResponse])
async def get_post_comments(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> list[CommentTreeResponse]:
    post = await _get_post_by_slug(slug, db)

    result = await db.execute(
        select(Comment)
        .where(
            Comment.post_id == post.id,
            Comment.parent_id.is_(None),
            Comment.status == CommentStatus.VISIBLE,
        )
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Comment.replies)
            .selectinload(Comment.replies)
            .selectinload(Comment.user),
        )
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [_comment_to_tree(c) for c in comments]


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: uuid.UUID,
    body: CommentUpdate,
    user: User = Depends(get_agent_or_admin),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(selectinload(Comment.user))
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(comment, field, value)

    await db.commit()
    await db.refresh(comment)

    return _comment_to_response(comment)


@router.get("/comments/pending", response_model=PendingCommentsResponse)
async def get_pending_comments(
    cursor: str | None = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> PendingCommentsResponse:
    query = (
        select(Comment)
        .where(
            Comment.response_status.in_([ResponseStatus.PENDING, ResponseStatus.NEEDS_RESPONSE])
        )
        .options(selectinload(Comment.user))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(limit + 1)
    )

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        query = query.where(
            (Comment.created_at > cursor_ts)
            | ((Comment.created_at == cursor_ts) & (Comment.id > cursor_id))
        )

    result = await db.execute(query)
    comments = list(result.scalars().all())

    next_cursor = None
    if len(comments) > limit:
        comments = comments[:limit]
        next_cursor = encode_cursor(comments[-1].created_at, comments[-1].id)

    return PendingCommentsResponse(
        items=[_comment_to_response(c) for c in comments],
        next_cursor=next_cursor,
    )


@router.get("/comments/flagged", response_model=PendingCommentsResponse)
async def get_flagged_comments(
    cursor: str | None = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> PendingCommentsResponse:
    query = (
        select(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
        .options(selectinload(Comment.user))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(limit + 1)
    )

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        query = query.where(
            (Comment.created_at > cursor_ts)
            | ((Comment.created_at == cursor_ts) & (Comment.id > cursor_id))
        )

    result = await db.execute(query)
    comments = list(result.scalars().all())

    next_cursor = None
    if len(comments) > limit:
        comments = comments[:limit]
        next_cursor = encode_cursor(comments[-1].created_at, comments[-1].id)

    return PendingCommentsResponse(
        items=[_comment_to_response(c) for c in comments],
        next_cursor=next_cursor,
    )
