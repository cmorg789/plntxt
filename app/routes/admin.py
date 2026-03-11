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
from app.models.post import Post, PostStatus
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Stats (JSON)
# ---------------------------------------------------------------------------


async def _collect_stats(db: AsyncSession) -> dict:
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
    total_views = await db.scalar(select(func.sum(Post.view_count)).select_from(Post))

    return {
        "post_count": post_count,
        "comment_count": comment_count,
        "pending_comments": pending_comments,
        "flagged_comments": flagged_comments,
        "user_count": user_count,
        "memory_count": memory_count,
        "total_views": total_views or 0,
    }


@router.get("/sidebar", response_class=HTMLResponse)
async def sidebar_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    stats = await _collect_stats(db)

    flagged_result = await db.execute(
        select(Comment)
        .where(Comment.status == CommentStatus.FLAGGED)
        .options(selectinload(Comment.user), selectinload(Comment.post))
        .order_by(Comment.created_at.desc())
        .limit(10)
    )
    flagged_comments = list(flagged_result.scalars().all())

    pending_result = await db.execute(
        select(Comment)
        .where(Comment.response_status.in_([ResponseStatus.PENDING, ResponseStatus.NEEDS_RESPONSE]))
        .options(selectinload(Comment.user), selectinload(Comment.post))
        .order_by(Comment.created_at.desc())
        .limit(10)
    )
    pending_comments = list(pending_result.scalars().all())

    top_posts_result = await db.execute(
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(Post.view_count.desc())
        .limit(5)
    )
    top_posts = list(top_posts_result.scalars().all())

    return templates.TemplateResponse(
        "admin/sidebar.html",
        {
            "request": request,
            "stats": stats,
            "flagged_comments": flagged_comments,
            "pending_comments": pending_comments,
            "top_posts": top_posts,
        },
    )


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    return await _collect_stats(db)



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

    # Re-query with all relationships needed for template rendering
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.post),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
    )
    return result.scalar_one()


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


def _render_inline_comment(request: Request, comment: Comment, user: User):
    return templates.TemplateResponse(
        "posts/_comment.html",
        {"request": request, "comment": comment, "current_user": user},
    )


@router.post("/comments/{comment_id}/approve", response_class=HTMLResponse)
async def approve_comment(
    comment_id: UUID,
    request: Request,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.VISIBLE, db)
    if source == "inline":
        return _render_inline_comment(request, comment, _user)
    if source == "sidebar":
        return HTMLResponse("")
    return HTMLResponse(_render_comment_row(comment))


@router.post("/comments/{comment_id}/hide", response_class=HTMLResponse)
async def hide_comment(
    comment_id: UUID,
    request: Request,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.HIDDEN, db)
    if source == "inline":
        return _render_inline_comment(request, comment, _user)
    if source == "sidebar":
        return HTMLResponse("")
    return HTMLResponse(_render_comment_row(comment))


@router.post("/comments/{comment_id}/flag", response_class=HTMLResponse)
async def flag_comment(
    comment_id: UUID,
    request: Request,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.FLAGGED, db)
    if source == "inline":
        return _render_inline_comment(request, comment, _user)
    if source == "sidebar":
        return HTMLResponse("")
    return HTMLResponse(_render_comment_row(comment))


@router.post("/comments/{comment_id}/delete", response_class=HTMLResponse)
async def delete_comment(
    comment_id: UUID,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    log_entry = ModerationLog(
        comment_id=comment.id,
        action=ModerationAction.HIDE,
        reason="Admin deleted comment",
    )
    db.add(log_entry)
    await db.delete(comment)
    await db.commit()
    return HTMLResponse("")


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
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()

    if config is None:
        raise HTTPException(status_code=404, detail="Config key not found")

    form_data = await request.form()

    # Reassemble the JSON object from individual form fields
    updated = dict(config.value)
    for field_key, original_value in config.value.items():
        form_key = f"field_{field_key}"
        if form_key in form_data:
            raw = form_data[form_key]
            # Coerce back to the original type
            if isinstance(original_value, int):
                try:
                    updated[field_key] = int(raw)
                except (ValueError, TypeError):
                    updated[field_key] = raw
            elif isinstance(original_value, float):
                try:
                    updated[field_key] = float(raw)
                except (ValueError, TypeError):
                    updated[field_key] = raw
            else:
                updated[field_key] = raw

    config.value = updated
    await db.commit()

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
