import secrets
from html import escape
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import RedirectResponse

from app.auth.dependencies import get_admin_user, get_agent_or_admin
from app.auth.passwords import hash_password
from app.db import get_db
from app.models.comment import Comment, CommentStatus, ResponseStatus
from app.models.config import Config
from app.models.memory import Memory
from app.models.moderation import Ban, ModerationAction, ModerationLog, ModerationRule, RuleType
from app.models.post import Post, PostStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Stats (JSON)
# ---------------------------------------------------------------------------


async def _collect_stats(db: AsyncSession) -> dict:
    stmt = select(
        select(func.count()).select_from(Post).correlate(None).scalar_subquery().label("post_count"),
        select(func.count()).select_from(Comment).correlate(None).scalar_subquery().label("comment_count"),
        select(func.count()).select_from(Comment).where(
            Comment.response_status == ResponseStatus.PENDING
        ).correlate(None).scalar_subquery().label("pending_comments"),
        select(func.count()).select_from(Comment).where(
            Comment.status == CommentStatus.FLAGGED
        ).correlate(None).scalar_subquery().label("flagged_comments"),
        select(func.count()).select_from(User).correlate(None).scalar_subquery().label("user_count"),
        select(func.count()).select_from(Memory).correlate(None).scalar_subquery().label("memory_count"),
        select(func.coalesce(func.sum(Post.view_count), 0)).select_from(Post).correlate(None).scalar_subquery().label("total_views"),
    )
    row = (await db.execute(stmt)).one()
    return {
        "post_count": row.post_count,
        "comment_count": row.comment_count,
        "pending_comments": row.pending_comments,
        "flagged_comments": row.flagged_comments,
        "user_count": row.user_count,
        "memory_count": row.memory_count,
        "total_views": row.total_views,
    }


@router.get("/sidebar", response_class=HTMLResponse)
async def sidebar_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
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
    admin_user: User = Depends(get_admin_user),
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
    admin_user: User = Depends(get_admin_user),
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
            "current_user": admin_user,
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
    if new_status == CommentStatus.HIDDEN:
        action = ModerationAction.HIDE
    elif new_status == CommentStatus.VISIBLE:
        action = ModerationAction.APPROVE
    else:
        action = ModerationAction.FLAG
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
    admin_user: User = Depends(get_admin_user),
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
    admin_user: User = Depends(get_admin_user),
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
    admin_user: User = Depends(get_admin_user),
):
    comment = await _update_comment_status(comment_id, CommentStatus.FLAGGED, db)
    if source == "inline":
        return _render_inline_comment(request, comment, _user)
    if source == "sidebar":
        return HTMLResponse("")
    return HTMLResponse(_render_comment_row(comment))


@router.post("/comments/{comment_id}/restore", response_class=HTMLResponse)
async def restore_comment(
    comment_id: UUID,
    request: Request,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(selectinload(Comment.user), selectinload(Comment.post))
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    old_status = comment.status
    comment.status = CommentStatus.VISIBLE
    comment.is_moderated = True
    comment.is_replied = False
    comment.response_status = ResponseStatus.NEEDS_RESPONSE

    log_entry = ModerationLog(
        comment_id=comment.id,
        action=ModerationAction.APPROVE,
        reason=f"Admin restored from {old_status.value} — queued for response",
    )
    db.add(log_entry)
    await db.commit()

    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.post),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
    )
    comment = result.scalar_one()

    if source == "inline":
        return _render_inline_comment(request, comment, admin_user)
    return _render_log_row_restored(comment)


def _render_log_row_restored(comment: Comment) -> str:
    body = comment.body[:120]
    if len(comment.body) > 120:
        body += "..."
    return f"""<tr>
  <td><span class="status-badge status-approve">approve</span></td>
  <td class="comment-body">{body}</td>
  <td>Admin restored — queued for response</td>
  <td class="nowrap">{comment.updated_at.strftime('%Y-%m-%d %H:%M') if hasattr(comment, 'updated_at') and comment.updated_at else ''}</td>
</tr>"""


@router.post("/comments/{comment_id}/delete", response_class=HTMLResponse)
async def delete_comment(
    comment_id: UUID,
    source: str = Query("table"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
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
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(Config))
    configs = {
        c.key: {"value": c.value, "updated_at": c.updated_at.isoformat()}
        for c in result.scalars().all()
        if c.key not in ("agent_personality", "email")
    }
    csrf_token = request.cookies.get("csrf_token", "")
    return templates.TemplateResponse(
        "admin/config.html",
        {"request": request, "current_user": admin_user, "configs": configs,
         "csrf_token": csrf_token, "message": None, "error": None},
    )


@router.post("/config/{key}/edit", response_class=HTMLResponse)
async def config_edit_form(
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
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

    return RedirectResponse(url="/admin/config", status_code=302)


@router.get("/config/json")
async def list_config_json(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_agent_or_admin),
):
    result = await db.execute(select(Config))
    configs = result.scalars().all()
    return {c.key: {"value": c.value, "updated_at": c.updated_at.isoformat()} for c in configs}


@router.patch("/config/{key}")
async def update_config(
    key: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
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


# ---------------------------------------------------------------------------
# Moderation Rules (HTML UI)
# ---------------------------------------------------------------------------


@router.get("/rules", response_class=HTMLResponse)
async def rules_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    # Active/inactive rules (not proposals)
    result = await db.execute(
        select(ModerationRule)
        .where(ModerationRule.proposed == False)  # noqa: E712
        .order_by(ModerationRule.created_at.desc())
    )
    rules = list(result.scalars().all())

    # Proposed rules awaiting review
    proposed_result = await db.execute(
        select(ModerationRule)
        .where(ModerationRule.proposed == True)  # noqa: E712
        .order_by(ModerationRule.created_at.desc())
    )
    proposed_rules = list(proposed_result.scalars().all())

    return templates.TemplateResponse(
        "admin/rules.html",
        {"request": request, "current_user": admin_user, "rules": rules, "proposed_rules": proposed_rules},
    )


def _render_rule_row(rule: ModerationRule) -> str:
    """Return an HTML table row for HTMX swap."""
    active_badge = (
        '<span class="status-badge status-visible">active</span>'
        if rule.active
        else '<span class="status-badge status-hidden">inactive</span>'
    )
    toggle_label = "Disable" if rule.active else "Enable"
    toggle_class = "btn-hide" if rule.active else "btn-approve"

    return f"""<tr id="rule-{rule.id}">
  <td><span class="status-badge">{rule.rule_type.value}</span></td>
  <td><code>{rule.value}</code></td>
  <td><span class="status-badge status-{rule.action.value}">{rule.action.value}</span></td>
  <td>{active_badge}</td>
  <td class="nowrap">{rule.created_at.strftime('%Y-%m-%d %H:%M')}</td>
  <td class="actions nowrap">
    <button
      hx-post="/admin/rules/{rule.id}/toggle"
      hx-target="#rule-{rule.id}"
      hx-swap="outerHTML"
      class="btn {toggle_class} btn-small"
    >{toggle_label}</button>
    <button
      hx-delete="/admin/rules/{rule.id}/delete"
      hx-target="#rule-{rule.id}"
      hx-swap="outerHTML"
      hx-confirm="Delete this rule?"
      class="btn btn-hide btn-small"
    >Delete</button>
  </td>
</tr>"""


@router.post("/rules/create", response_class=HTMLResponse)
async def create_rule_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    form_data = await request.form()
    rule_type = form_data.get("rule_type", "keyword")
    value = form_data.get("value", "").strip()
    action = form_data.get("action", "flag")

    if not value:
        raise HTTPException(status_code=422, detail="Value is required")

    rule = ModerationRule(
        rule_type=RuleType(rule_type),
        value=value,
        action=ModerationAction(action),
        active=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return HTMLResponse(_render_rule_row(rule))


@router.post("/rules/{rule_id}/approve", response_class=HTMLResponse)
async def approve_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(ModerationRule).where(ModerationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.proposed = False
    rule.active = True
    await db.commit()
    await db.refresh(rule)
    # Return empty to remove from proposed table; it'll show up on next full page load
    return HTMLResponse("")


@router.post("/rules/{rule_id}/toggle", response_class=HTMLResponse)
async def toggle_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(ModerationRule).where(ModerationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.active = not rule.active
    await db.commit()
    await db.refresh(rule)
    return HTMLResponse(_render_rule_row(rule))


@router.delete("/rules/{rule_id}/delete", response_class=HTMLResponse)
async def delete_rule_html(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(ModerationRule).where(ModerationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()
    return HTMLResponse("")


# ---------------------------------------------------------------------------
# User management (HTML + JSON)
# ---------------------------------------------------------------------------


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    stmt = select(User)

    if q and q.strip():
        search = f"%{q.strip()}%"
        stmt = stmt.where(User.username.ilike(search) | User.email.ilike(search))

    if cursor:
        try:
            cursor_id = UUID(cursor)
            cursor_row = await db.scalar(
                select(User.created_at).where(User.id == cursor_id)
            )
            if cursor_row is not None:
                stmt = stmt.where(
                    (User.created_at < cursor_row)
                    | ((User.created_at == cursor_row) & (User.id < cursor_id))
                )
        except (ValueError, TypeError):
            pass

    stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    users = list(result.scalars().all())

    next_cursor: str | None = None
    if len(users) > limit:
        users = users[:limit]
        next_cursor = str(users[-1].id)

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "current_user": admin_user,
            "users": users,
            "roles": list(UserRole),
            "next_cursor": next_cursor,
            "prev_cursor": cursor,
            "q": q,
        },
    )


def _render_user_row(request: Request, user: User):
    """Return a TemplateResponse rendering the user row partial for HTMX swap."""
    return templates.TemplateResponse(
        "admin/_user_row.html",
        {"request": request, "user": user, "roles": list(UserRole)},
    )


@router.patch("/users/{user_id}/role", response_class=HTMLResponse)
async def update_user_role(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    form_data = await request.form()
    new_role = form_data.get("role")
    if new_role and new_role in {r.value for r in UserRole}:
        user.role = UserRole(new_role)
        await db.commit()
        await db.refresh(user)

    return _render_user_row(request, user)


@router.post("/users/{user_id}/ban", response_class=HTMLResponse)
async def ban_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Cannot ban an admin")

    ban = Ban(user_id=user.id, reason="Banned via admin panel")
    db.add(ban)
    user.is_banned = True
    await db.commit()
    await db.refresh(user)
    return _render_user_row(request, user)


@router.post("/users/{user_id}/unban", response_class=HTMLResponse)
async def unban_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Remove all active bans
    await db.execute(delete(Ban).where(Ban.user_id == user.id))

    user.is_banned = False
    await db.commit()
    await db.refresh(user)
    return _render_user_row(request, user)


@router.post("/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_user_password(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = secrets.token_urlsafe(12)
    user.password_hash = hash_password(temp_password)
    await db.commit()

    return HTMLResponse(
        f'<h3>Password Reset</h3>'
        f'<p>Temporary password for <strong>{escape(user.username)}</strong>:</p>'
        f'<code class="credential-display">{escape(temp_password)}</code>'
        f'<p class="hint">This will not be shown again.</p>'
    )


@router.post("/users/{user_id}/generate-api-key", response_class=HTMLResponse)
async def generate_api_key(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.AGENT:
        raise HTTPException(status_code=400, detail="API keys are for agent users only")

    api_key = f"plntxt_{secrets.token_urlsafe(32)}"
    user.api_key = api_key
    await db.commit()

    return HTMLResponse(
        f'<h3>API Key Generated</h3>'
        f'<p>API key for <strong>{escape(user.username)}</strong>:</p>'
        f'<code class="credential-display">{escape(api_key)}</code>'
        f'<p class="hint">This will not be shown again. Use as <code>X-API-Key</code> header.</p>'
    )


@router.delete("/users/{user_id}", response_class=HTMLResponse)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Cannot delete an admin")

    await db.delete(user)
    await db.commit()
    return HTMLResponse("")


# ---------------------------------------------------------------------------
# Moderation log viewer (HTML)
# ---------------------------------------------------------------------------


@router.get("/log", response_class=HTMLResponse)
async def moderation_log_page(
    request: Request,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    stmt = (
        select(ModerationLog)
        .options(selectinload(ModerationLog.comment))
    )

    if cursor:
        try:
            cursor_id = UUID(cursor)
            cursor_row = await db.scalar(
                select(ModerationLog.created_at).where(ModerationLog.id == cursor_id)
            )
            if cursor_row is not None:
                stmt = stmt.where(
                    (ModerationLog.created_at < cursor_row)
                    | ((ModerationLog.created_at == cursor_row) & (ModerationLog.id < cursor_id))
                )
        except (ValueError, TypeError):
            pass

    stmt = stmt.order_by(ModerationLog.created_at.desc(), ModerationLog.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    entries = list(result.scalars().all())

    next_cursor: str | None = None
    if len(entries) > limit:
        entries = entries[:limit]
        next_cursor = str(entries[-1].id)

    return templates.TemplateResponse(
        "admin/log.html",
        {
            "request": request,
            "current_user": admin_user,
            "entries": entries,
            "next_cursor": next_cursor,
            "prev_cursor": cursor,
        },
    )


# ---------------------------------------------------------------------------
# Voice tuning (HTML)
# ---------------------------------------------------------------------------


async def _load_personality(db: AsyncSession) -> dict:
    result = await db.execute(select(Config).where(Config.key == "agent_personality"))
    config = result.scalar_one_or_none()
    if config is None:
        return {}
    return config.value if isinstance(config.value, dict) else {}


@router.get("/voice", response_class=HTMLResponse)
async def voice_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    personality = await _load_personality(db)
    return templates.TemplateResponse(
        "admin/voice.html",
        {"request": request, "current_user": admin_user, "personality": personality, "message": None},
    )


@router.post("/voice", response_class=HTMLResponse)
async def voice_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    form_data = await request.form()

    # Parse comma-separated lists
    interests_raw = form_data.get("interests", "")
    avoid_raw = form_data.get("avoid", "")

    personality = {
        "system_prompt": form_data.get("system_prompt", ""),
        "writing_style": form_data.get("writing_style", ""),
        "tone": form_data.get("tone", ""),
        "interests": [s.strip() for s in interests_raw.split(",") if s.strip()],
        "avoid": [s.strip() for s in avoid_raw.split(",") if s.strip()],
    }

    result = await db.execute(select(Config).where(Config.key == "agent_personality"))
    config = result.scalar_one_or_none()
    if config is None:
        config = Config(key="agent_personality", value=personality)
        db.add(config)
    else:
        # Preserve any existing keys not managed by this form
        updated = dict(config.value) if isinstance(config.value, dict) else {}
        updated.update(personality)
        config.value = updated

    await db.commit()
    return RedirectResponse(url="/admin/voice", status_code=302)


@router.post("/voice/preview", response_class=HTMLResponse)
async def voice_preview(
    request: Request,
    admin_user: User = Depends(get_admin_user),
):
    form_data = await request.form()

    system_prompt = form_data.get("system_prompt", "")
    writing_style = form_data.get("writing_style", "")
    tone = form_data.get("tone", "")
    interests = form_data.get("interests", "")
    avoid = form_data.get("avoid", "")
    topic = form_data.get("preview_topic", "").strip()

    if not topic:
        return HTMLResponse('<p class="form-error">Enter a topic to preview.</p>')

    # Build a personality description for the prompt
    personality_parts = []
    if system_prompt:
        personality_parts.append(system_prompt)
    if writing_style:
        personality_parts.append(f"Writing style: {writing_style}")
    if tone:
        personality_parts.append(f"Tone: {tone}")
    if interests:
        personality_parts.append(f"Interests: {interests}")
    if avoid:
        personality_parts.append(f"Avoid: {avoid}")

    system = "\n".join(personality_parts) if personality_parts else "You are a blog author."

    try:
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system,
            messages=[
                {"role": "user", "content": f"Write a single blog paragraph about: {topic}"}
            ],
        )
        text = message.content[0].text
    except Exception as e:
        return HTMLResponse(f'<p class="form-error">Preview failed: {e}</p>')

    return HTMLResponse(
        f'<div class="preview-sample"><p>{text}</p></div>'
    )


# ---------------------------------------------------------------------------
# Email Settings (dedicated page)
# ---------------------------------------------------------------------------


async def _load_email_config(db: AsyncSession) -> dict:
    result = await db.execute(select(Config).where(Config.key == "email"))
    config = result.scalar_one_or_none()
    if config is None:
        return {}
    return config.value if isinstance(config.value, dict) else {}


@router.get("/email", response_class=HTMLResponse)
async def email_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    email_config = await _load_email_config(db)
    return templates.TemplateResponse(
        "admin/email.html",
        {"request": request, "current_user": admin_user, "email_config": email_config,
         "message": None, "error": None},
    )


@router.post("/email", response_class=HTMLResponse)
async def email_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    form_data = await request.form()

    email_config = {
        "smtp_host": form_data.get("smtp_host", ""),
        "smtp_port": int(form_data.get("smtp_port", 587)),
        "smtp_user": form_data.get("smtp_user", ""),
        "smtp_password": form_data.get("smtp_password", ""),
        "smtp_from": form_data.get("smtp_from", ""),
        "use_tls": form_data.get("use_tls", "true") == "true",
        "verification_token_expire_hours": int(form_data.get("verification_token_expire_hours", 48)),
    }

    result = await db.execute(select(Config).where(Config.key == "email"))
    config = result.scalar_one_or_none()
    if config is None:
        config = Config(key="email", value=email_config)
        db.add(config)
    else:
        config.value = email_config

    await db.commit()

    return templates.TemplateResponse(
        "admin/email.html",
        {"request": request, "current_user": admin_user, "email_config": email_config,
         "message": "Email settings saved.", "error": None},
    )


@router.post("/email/test", response_class=HTMLResponse)
async def email_test(
    request: Request,
    admin_user: User = Depends(get_admin_user),
):
    form_data = await request.form()
    to_email = form_data.get("test_email", "").strip()

    if not to_email:
        return HTMLResponse('<p class="form-error">Enter an email address.</p>')

    smtp_host = form_data.get("smtp_host", "").strip()
    if not smtp_host:
        return HTMLResponse('<p class="form-error">SMTP host is not configured. Save settings first.</p>')

    from email.message import EmailMessage
    import aiosmtplib

    msg = EmailMessage()
    msg["Subject"] = "Test email from plntxt"
    msg["From"] = form_data.get("smtp_from", "noreply@plntxt.dev")
    msg["To"] = to_email
    msg.set_content("This is a test email from your plntxt installation. If you received this, email is working.")

    smtp_port = int(form_data.get("smtp_port", 587))
    smtp_user = form_data.get("smtp_user", "").strip()
    smtp_password = form_data.get("smtp_password", "")
    use_tls = form_data.get("use_tls", "true") == "true"

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            start_tls=use_tls,
        )
    except Exception as e:
        return HTMLResponse(f'<p class="form-error">Failed: {e}</p>')

    return HTMLResponse(f'<p class="form-success">Test email sent to {to_email}.</p>')
