from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_admin_user
from app.db import get_db
from app.models.comment import Comment, CommentStatus, ResponseStatus
from app.models.config import Config
from app.models.memory import Memory
from app.models.moderation import ModerationAction, ModerationLog
from app.models.post import Post
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Stats (JSON)
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    post_count = await db.scalar(select(func.count()).select_from(Post))
    comment_count = await db.scalar(select(func.count()).select_from(Comment))
    pending_comments = await db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.response_status == ResponseStatus.PENDING)
    )
    flagged_comments = await db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
    )
    user_count = await db.scalar(select(func.count()).select_from(User))
    memory_count = await db.scalar(select(func.count()).select_from(Memory))

    return {
        "post_count": post_count,
        "comment_count": comment_count,
        "pending_comments": pending_comments,
        "flagged_comments": flagged_comments,
        "user_count": user_count,
        "memory_count": memory_count,
    }


# ---------------------------------------------------------------------------
# Dashboard (HTML)
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    # Gather stats
    post_count = await db.scalar(select(func.count()).select_from(Post))
    comment_count = await db.scalar(select(func.count()).select_from(Comment))
    pending_comments = await db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.response_status == ResponseStatus.PENDING)
    )
    flagged_count = await db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
    )
    user_count = await db.scalar(select(func.count()).select_from(User))
    memory_count = await db.scalar(select(func.count()).select_from(Memory))

    stats = {
        "post_count": post_count,
        "comment_count": comment_count,
        "pending_comments": pending_comments,
        "flagged_comments": flagged_count,
        "user_count": user_count,
        "memory_count": memory_count,
    }

    # Recent posts (last 5)
    recent_posts_result = await db.execute(
        select(Post).order_by(Post.created_at.desc()).limit(5)
    )
    recent_posts = list(recent_posts_result.scalars().all())

    # Recent flagged comments (last 5) with user and post eagerly loaded
    flagged_result = await db.execute(
        select(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
        .options(selectinload(Comment.user), selectinload(Comment.post))
        .order_by(Comment.created_at.desc())
        .limit(5)
    )
    flagged_comments = list(flagged_result.scalars().all())

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "stats": stats,
            "recent_posts": recent_posts,
            "flagged_comments": flagged_comments,
        },
    )


# ---------------------------------------------------------------------------
# Moderation queue (HTML)
# ---------------------------------------------------------------------------


@router.get("/moderation", response_class=HTMLResponse)
async def moderation_queue(
    request: Request,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    stmt = (
        select(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
        .options(selectinload(Comment.user), selectinload(Comment.post))
    )

    if cursor:
        try:
            cursor_id = UUID(cursor)
            # Fetch the cursor comment's created_at for keyset pagination
            cursor_row = await db.scalar(
                select(Comment.created_at).where(Comment.id == cursor_id)
            )
            if cursor_row is not None:
                stmt = stmt.where(
                    (Comment.created_at < cursor_row)
                    | ((Comment.created_at == cursor_row) & (Comment.id < cursor_id))
                )
        except (ValueError, TypeError):
            pass

    stmt = stmt.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    comments = list(result.scalars().all())

    next_cursor: str | None = None
    if len(comments) > limit:
        comments = comments[:limit]
        next_cursor = str(comments[-1].id)

    return templates.TemplateResponse(
        "admin/moderation.html",
        {
            "request": request,
            "comments": comments,
            "next_cursor": next_cursor,
            "prev_cursor": cursor,
        },
    )


# ---------------------------------------------------------------------------
# Comment actions (HTMX partials)
# ---------------------------------------------------------------------------


async def _update_comment_status(
    comment_id: UUID,
    new_status: CommentStatus,
    db: AsyncSession,
) -> Comment:
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(selectinload(Comment.user), selectinload(Comment.post))
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    old_status = comment.status
    comment.status = new_status

    # Log the moderation action
    action = ModerationAction.HIDE if new_status == CommentStatus.HIDDEN else ModerationAction.FLAG
    log_entry = ModerationLog(
        comment_id=comment.id,
        action=action,
        reason=f"Admin changed status from {old_status.value} to {new_status.value}",
    )
    db.add(log_entry)

    await db.commit()
    await db.refresh(comment)
    return comment


def _render_comment_row(comment: Comment) -> str:
    """Return an HTML table row snippet for HTMX swap."""
    status_val = comment.status.value
    post_slug = comment.post.slug if comment.post else ""
    post_title = comment.post.title[:40] if comment.post else ""
    if comment.post and len(comment.post.title) > 40:
        post_title += "..."
    username = comment.user.username if comment.user else "unknown"
    body = comment.body[:200]
    if len(comment.body) > 200:
        body += "..."
    created = comment.created_at.strftime("%Y-%m-%d %H:%M")

    return f"""<tr id="comment-{comment.id}">
  <td class="comment-body">{body}</td>
  <td><a href="/posts/{post_slug}">{post_title}</a></td>
  <td>{username}</td>
  <td class="nowrap">{created}</td>
  <td><span class="status-badge status-{status_val}">{status_val}</span></td>
  <td class="actions nowrap">
    <button
      hx-post="/admin/comments/{comment.id}/approve"
      hx-target="#comment-{comment.id}"
      hx-swap="outerHTML"
      class="btn btn-approve"
    >Approve</button>
    <button
      hx-post="/admin/comments/{comment.id}/hide"
      hx-target="#comment-{comment.id}"
      hx-swap="outerHTML"
      class="btn btn-hide"
    >Hide</button>
  </td>
</tr>"""


@router.post("/comments/{comment_id}/approve", response_class=HTMLResponse)
async def approve_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.VISIBLE, db)
    return HTMLResponse(_render_comment_row(comment))


@router.post("/comments/{comment_id}/hide", response_class=HTMLResponse)
async def hide_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.HIDDEN, db)
    return HTMLResponse(_render_comment_row(comment))


# ---------------------------------------------------------------------------
# Config management (HTML + JSON)
# ---------------------------------------------------------------------------


@router.get("/config", response_class=HTMLResponse)
async def config_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Config))
    configs = {c.key: {"value": c.value, "updated_at": c.updated_at.isoformat()} for c in result.scalars().all()}
    csrf_token = request.cookies.get("csrf_token", "")
    return templates.TemplateResponse(
        "admin/config.html",
        {"request": request, "configs": configs, "csrf_token": csrf_token,
         "message": None, "error": None},
    )


@router.post("/config/{key}/edit", response_class=HTMLResponse)
async def config_edit_form(
    key: str,
    request: Request,
    value: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    import json as _json

    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()

    if config is None:
        raise HTTPException(status_code=404, detail="Config key not found")

    try:
        parsed = _json.loads(value)
    except _json.JSONDecodeError as e:
        # Re-render with error
        all_result = await db.execute(select(Config))
        configs = {c.key: {"value": c.value, "updated_at": c.updated_at.isoformat()} for c in all_result.scalars().all()}
        csrf_token = request.cookies.get("csrf_token", "")
        return templates.TemplateResponse(
            "admin/config.html",
            {"request": request, "configs": configs, "csrf_token": csrf_token,
             "message": None, "error": f"Invalid JSON for '{key}': {e}"},
        )

    config.value = parsed
    await db.commit()

    # Redirect back to config page with success
    from starlette.responses import RedirectResponse as _Redirect
    return _Redirect(url="/admin/config", status_code=302)


@router.get("/config/json")
async def list_config_json(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Config))
    configs = result.scalars().all()
    return {c.key: {"value": c.value, "updated_at": c.updated_at.isoformat()} for c in configs}


@router.patch("/config/{key}")
async def update_config(
    key: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config key not found")

    if "value" not in body:
        raise HTTPException(status_code=422, detail="Request body must contain 'value'")

    config.value = body["value"]
    await db.commit()
    await db.refresh(config)
    return {"key": config.key, "value": config.value, "updated_at": config.updated_at.isoformat()}
