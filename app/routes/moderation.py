from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.dependencies import get_admin_user, get_agent_or_admin
from app.models.user import UserRole
from app.db import get_db
from app.models.moderation import Ban, ModerationLog, ModerationRule
from app.pagination import decode_cursor, encode_cursor
from app.models.schemas.moderation import (
    BanCreate,
    BanResponse,
    ModerationLogListResponse,
    ModerationLogResponse,
    ModerationRuleCreate,
    ModerationRuleResponse,
    ModerationRuleUpdate,
)
from app.models.user import User

router = APIRouter(prefix="/moderation", tags=["moderation"])



# --- Moderation Log ---


@router.get("/log", response_model=ModerationLogListResponse)
async def list_moderation_log(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    stmt = select(ModerationLog)

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            (ModerationLog.created_at < cursor_ts)
            | ((ModerationLog.created_at == cursor_ts) & (ModerationLog.id < cursor_id))
        )

    stmt = stmt.order_by(ModerationLog.created_at.desc(), ModerationLog.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    entries = list(result.scalars().all())

    next_cursor: str | None = None
    if len(entries) > limit:
        entries = entries[:limit]
        next_cursor = encode_cursor(entries[-1].created_at, entries[-1].id)

    return ModerationLogListResponse(
        items=[ModerationLogResponse.model_validate(e) for e in entries],
        next_cursor=next_cursor,
    )


# --- Moderation Rules ---


@router.get("/rules", response_model=list[ModerationRuleResponse])
async def list_rules(
    active: bool | None = Query(None),
    proposed: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    stmt = select(ModerationRule)
    if active is not None:
        stmt = stmt.where(ModerationRule.active == active)
    if proposed is not None:
        stmt = stmt.where(ModerationRule.proposed == proposed)
    stmt = stmt.order_by(ModerationRule.created_at.desc())

    result = await db.execute(stmt)
    rules = result.scalars().all()
    return [ModerationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=ModerationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: ModerationRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_agent_or_admin),
):
    # Agents can only propose rules, never create active ones directly
    is_agent = user.role == UserRole.AGENT
    rule = ModerationRule(
        rule_type=data.rule_type,
        value=data.value,
        action=data.action,
        active=False if is_agent else data.active,
        proposed=True if is_agent else data.proposed,
        proposed_reason=data.proposed_reason,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ModerationRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=ModerationRuleResponse)
async def update_rule(
    rule_id: UUID,
    data: ModerationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(ModerationRule).where(ModerationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    return ModerationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(select(ModerationRule).where(ModerationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Bans ---


@router.get("/bans", response_model=list[BanResponse])
async def list_bans(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    now = datetime.now(timezone.utc)
    stmt = (
        select(Ban)
        .options(joinedload(Ban.user))
        .where((Ban.expires_at.is_(None)) | (Ban.expires_at > now))
        .order_by(Ban.created_at.desc())
    )

    result = await db.execute(stmt)
    bans = result.scalars().all()
    return [BanResponse.model_validate(b) for b in bans]


@router.post("/bans", response_model=BanResponse, status_code=status.HTTP_201_CREATED)
async def create_ban(
    data: BanCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    # Verify user exists
    result = await db.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    ban = Ban(
        user_id=data.user_id,
        reason=data.reason,
        expires_at=data.expires_at,
    )
    db.add(ban)
    user.is_banned = True

    await db.commit()
    await db.refresh(ban)
    return BanResponse.model_validate(ban)


@router.delete("/bans/{ban_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ban(
    ban_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_admin_user),
):
    result = await db.execute(
        select(Ban).options(joinedload(Ban.user)).where(Ban.id == ban_id)
    )
    ban = result.scalar_one_or_none()
    if ban is None:
        raise HTTPException(status_code=404, detail="Ban not found")

    ban.user.is_banned = False
    await db.delete(ban)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
