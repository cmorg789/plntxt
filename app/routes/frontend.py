from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user, get_optional_user
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.auth.session import build_session, set_session_cookie
from app.db import get_db
from app.models.comment import AuthorType, Comment, CommentStatus
from app.pagination import decode_cursor, encode_cursor
from app.models.post import Post, PostStatus
from app.models.user import User, UserRole

router = APIRouter(tags=["frontend"])
templates = Jinja2Templates(directory="app/templates")



@router.get("/")
async def index():
    return RedirectResponse(url="/posts", status_code=302)


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
        },
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

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()

    token = create_access_token(user.id)
    db.add(build_session(user.id, token))
    await db.commit()

    response = RedirectResponse(url="/posts", status_code=302)
    set_session_cookie(response, token)
    return response
