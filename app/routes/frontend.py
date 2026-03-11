from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user, get_optional_user
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.auth.session import build_session, set_session_cookie
from app.db import get_db
from app.email import (
    generate_verification_token,
    send_verification_email,
    verification_token_expiry,
)
from app.services.embeddings import embed_query
from app.models.comment import AuthorType, Comment, CommentStatus
from app.models.config import Config
from app.models.revision import PostRevision
from app.models.series import Series
from app.pagination import decode_cursor, encode_cursor
from app.models.post import Post, PostStatus
from app.models.user import User, UserRole

router = APIRouter(tags=["frontend"])
templates = Jinja2Templates(directory="app/templates")



@router.get("/")
async def index():
    return RedirectResponse(url="/posts", status_code=302)


@router.get("/about")
async def about_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(select(Config).where(Config.key == "about_page"))
    config_row = result.scalar_one_or_none()
    content = ""
    if config_row and config_row.value:
        content = config_row.value.get("content", "")
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "content": content, "current_user": current_user},
    )


@router.get("/search")
async def search_page(
    request: Request,
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    posts = []
    if q and len(q.strip()) > 0:
        q = q.strip()
        query_vec = embed_query(q)
        stmt = (
            select(Post)
            .where(
                Post.status == PostStatus.PUBLISHED,
                Post.embedding.isnot(None),
            )
            .order_by(Post.embedding.cosine_distance(query_vec))
            .limit(20)
        )
        result = await db.execute(stmt)
        posts = list(result.scalars().all())
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "posts": posts, "q": q or "", "current_user": current_user},
    )


@router.get("/posts")
async def post_list(
    request: Request,
    cursor: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    stmt = (
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc(), Post.id.desc())
    )

    if tag:
        stmt = stmt.where(Post.tags.any(tag))

    if cursor:
        try:
            cursor_ts, cursor_id = decode_cursor(cursor)
        except HTTPException:
            cursor_ts = cursor_id = None
        if cursor_ts and cursor_id:
            stmt = stmt.where(
                (Post.published_at < cursor_ts)
                | ((Post.published_at == cursor_ts) & (Post.id < cursor_id))
            )

    stmt = stmt.limit(limit + 1)

    result = await db.execute(stmt)
    posts = list(result.scalars().all())

    next_cursor = None
    if len(posts) > limit:
        posts = posts[:limit]
        ts = posts[-1].published_at if posts[-1].published_at else posts[-1].created_at
        next_cursor = encode_cursor(ts, posts[-1].id)

    return templates.TemplateResponse(
        "posts/list.html",
        {
            "request": request,
            "posts": posts,
            "next_cursor": next_cursor,
            "prev_cursor": None,
            "tag": tag,
            "current_user": current_user,
        },
    )


@router.get("/posts/{slug}")
async def post_detail(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.PUBLISHED)
    )
    post = result.scalar_one_or_none()
    if post is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Post not found")

    # Increment view count atomically
    await db.execute(
        sql_update(Post).where(Post.id == post.id).values(view_count=Post.view_count + 1)
    )
    await db.commit()

    # Re-fetch with series loaded for nav
    result = await db.execute(
        select(Post)
        .where(Post.id == post.id)
        .options(selectinload(Post.series).selectinload(Series.posts))
    )
    post = result.scalar_one()

    # Series navigation
    prev_series_post = None
    next_series_post = None
    if post.series:
        siblings = sorted(
            [p for p in post.series.posts if p.status == PostStatus.PUBLISHED and p.id != post.id],
            key=lambda p: p.series_position or 0,
        )
        for s in siblings:
            if (s.series_position or 0) < (post.series_position or 0):
                prev_series_post = s
            elif (s.series_position or 0) > (post.series_position or 0) and next_series_post is None:
                next_series_post = s

    # Load comment tree: admins see all statuses, others see only visible
    is_admin = current_user and current_user.role == UserRole.ADMIN
    comment_query = select(Comment).where(
        Comment.post_id == post.id,
        Comment.parent_id.is_(None),
    )
    if not is_admin:
        comment_query = comment_query.where(Comment.status == CommentStatus.VISIBLE)
    comment_result = await db.execute(
        comment_query
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies, recursion_depth=-1)
            .selectinload(Comment.user),
        )
        .order_by(Comment.created_at.asc())
    )
    comments = comment_result.scalars().all()

    return templates.TemplateResponse(
        "posts/detail.html",
        {
            "request": request,
            "post": post,
            "comments": comments,
            "current_user": current_user,
            "prev_series_post": prev_series_post,
            "next_series_post": next_series_post,
        },
    )


@router.get("/posts/{slug}/revisions")
async def post_revisions_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.PUBLISHED)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    revs_result = await db.execute(
        select(PostRevision)
        .where(PostRevision.post_id == post.id)
        .order_by(PostRevision.revision_number.desc())
    )
    revisions = list(revs_result.scalars().all())

    return templates.TemplateResponse(
        "posts/revisions.html",
        {"request": request, "post": post, "revisions": revisions, "current_user": current_user},
    )


@router.get("/series/{slug}")
async def series_detail_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    from app.models.series import Series
    result = await db.execute(
        select(Series).where(Series.slug == slug).options(selectinload(Series.posts))
    )
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    posts = sorted(
        [p for p in series.posts if p.status == PostStatus.PUBLISHED],
        key=lambda p: p.series_position or 0,
    )

    return templates.TemplateResponse(
        "series/detail.html",
        {"request": request, "series": series, "posts": posts, "current_user": current_user},
    )


# ---------------------------------------------------------------------------
# HTMX form handlers for comments (accept form data, return HTML partials)
# ---------------------------------------------------------------------------

def _render_comment_html(comment: Comment) -> str:
    """Render a single comment as HTML for HTMX swap."""
    author_class = "comment-author-ai" if comment.author_type == AuthorType.AI else ""
    ai_badge = '<span class="ai-badge">AI</span>' if comment.author_type == AuthorType.AI else ""
    created = comment.created_at.strftime("%B %-d, %Y at %-I:%M %p")
    username = comment.user.username if comment.user else "unknown"

    return f"""<div class="comment" id="comment-{comment.id}">
    <div class="comment-header">
        <span class="comment-author {author_class}">{username} {ai_badge}</span>
        <time datetime="{comment.created_at.isoformat()}">{created}</time>
    </div>
    <div class="comment-body markdown-content">{comment.body}</div>
    <div class="comment-replies"></div>
</div>"""


@router.post("/posts/{slug}/comments", response_class=HTMLResponse)
async def create_comment_form(
    slug: str,
    request: Request,
    body: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.email_verified and user.role == UserRole.USER:
        raise HTTPException(status_code=403, detail="Please verify your email before commenting.")

    result = await db.execute(select(Post).where(Post.slug == slug))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    author_type = AuthorType.AI if user.role == UserRole.AGENT else AuthorType.HUMAN
    comment = Comment(
        post_id=post.id,
        user_id=user.id,
        author_type=author_type,
        body=body,
        ip_address=request.client.host if request.client else None,
    )
    db.add(comment)
    await db.flush()
    comment.user = user
    await db.commit()

    return HTMLResponse(_render_comment_html(comment))


@router.post("/comments/{comment_id}/reply", response_class=HTMLResponse)
async def reply_comment_form(
    comment_id: UUID,
    request: Request,
    body: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.email_verified and user.role == UserRole.USER:
        raise HTTPException(status_code=403, detail="Please verify your email before commenting.")

    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    author_type = AuthorType.AI if user.role == UserRole.AGENT else AuthorType.HUMAN
    reply = Comment(
        post_id=parent.post_id,
        parent_id=parent.id,
        user_id=user.id,
        author_type=author_type,
        body=body,
        ip_address=request.client.host if request.client else None,
    )
    db.add(reply)
    await db.flush()
    reply.user = user
    await db.commit()

    return HTMLResponse(_render_comment_html(reply))


# ---------------------------------------------------------------------------
# Auth form pages (HTML login / register)
# ---------------------------------------------------------------------------


@router.get("/auth/login")
async def login_page(
    request: Request,
    current_user: User | None = Depends(get_optional_user),
):
    if current_user:
        return RedirectResponse(url="/posts", status_code=302)
    csrf_token = request.cookies.get("csrf_token", "")
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "csrf_token": csrf_token, "error": None, "email": None,
         "current_user": None},
    )


@router.post("/auth/login/form")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    csrf_token = request.cookies.get("csrf_token", "")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "csrf_token": csrf_token,
             "error": "Invalid email or password.", "email": email,
             "current_user": None},
            status_code=401,
        )

    if user.is_banned:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "csrf_token": csrf_token,
             "error": "This account has been banned.", "email": email,
             "current_user": None},
            status_code=403,
        )

    token = create_access_token(user.id)
    db.add(build_session(user.id, token))
    await db.commit()

    response = RedirectResponse(url="/posts", status_code=302)
    set_session_cookie(response, token)
    return response


@router.get("/auth/register")
async def register_page(
    request: Request,
    current_user: User | None = Depends(get_optional_user),
):
    if current_user:
        return RedirectResponse(url="/posts", status_code=302)
    csrf_token = request.cookies.get("csrf_token", "")
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request, "csrf_token": csrf_token, "error": None,
         "username": None, "email": None, "current_user": None},
    )


@router.post("/auth/register/form")
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    csrf_token = request.cookies.get("csrf_token", "")

    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "csrf_token": csrf_token,
             "error": "Password must be at least 8 characters.",
             "username": username, "email": email, "current_user": None},
            status_code=400,
        )

    existing = await db.execute(
        select(User).where((User.email == email) | (User.username == username))
    )
    existing_user = existing.scalar_one_or_none()
    if existing_user is not None:
        error = (
            "Email already registered."
            if existing_user.email == email
            else "Username already taken."
        )
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "csrf_token": csrf_token, "error": error,
             "username": username, "email": email, "current_user": None},
            status_code=409,
        )

    token = generate_verification_token()
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        verification_token=token,
        verification_token_expires_at=verification_token_expiry(),
    )
    db.add(user)
    await db.flush()

    session_token = create_access_token(user.id)
    db.add(build_session(user.id, session_token))
    await db.commit()

    await send_verification_email(email, username, token)

    response = RedirectResponse(url="/auth/verify-pending", status_code=302)
    set_session_cookie(response, session_token)
    return response


@router.get("/auth/verify-pending")
async def verify_pending_page(
    request: Request,
    current_user: User | None = Depends(get_optional_user),
):
    if current_user and current_user.email_verified:
        return RedirectResponse(url="/posts", status_code=302)
    csrf_token = request.cookies.get("csrf_token", "")
    email = current_user.email if current_user else ""
    return templates.TemplateResponse(
        "auth/verify_pending.html",
        {"request": request, "csrf_token": csrf_token, "email": email,
         "success": None, "error": None, "current_user": current_user},
    )


@router.get("/auth/verify")
async def verify_email(
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    from datetime import datetime, timezone

    result = await db.execute(
        select(User).where(User.verification_token == token)
    )
    user = result.scalar_one_or_none()

    if user is None:
        return templates.TemplateResponse(
            "auth/verify_result.html",
            {"request": request, "success": None,
             "error": "Invalid verification link.", "current_user": current_user},
            status_code=400,
        )

    if user.verification_token_expires_at and user.verification_token_expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse(
            "auth/verify_result.html",
            {"request": request, "success": None,
             "error": "This verification link has expired. Please log in and request a new one.",
             "current_user": current_user},
            status_code=400,
        )

    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    await db.commit()

    return templates.TemplateResponse(
        "auth/verify_result.html",
        {"request": request,
         "success": "Your email has been verified. You're all set!",
         "error": None, "current_user": current_user},
    )


@router.post("/auth/resend-verification")
async def resend_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    csrf_token = request.cookies.get("csrf_token", "")

    if current_user.email_verified:
        return RedirectResponse(url="/posts", status_code=302)

    token = generate_verification_token()
    current_user.verification_token = token
    current_user.verification_token_expires_at = verification_token_expiry()
    await db.commit()

    await send_verification_email(current_user.email, current_user.username, token)

    return templates.TemplateResponse(
        "auth/verify_pending.html",
        {"request": request, "csrf_token": csrf_token, "email": current_user.email,
         "success": "Verification email resent.", "error": None,
         "current_user": current_user},
    )
