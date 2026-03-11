from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.moderation import ModerationAction, RuleType


# --- Moderation Log ---

class ModerationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    comment_id: UUID
    action: ModerationAction
    reason: str | None
    created_at: datetime


class ModerationLogListResponse(BaseModel):
    items: list[ModerationLogResponse]
    next_cursor: str | None


# --- Moderation Rules ---

class ModerationRuleCreate(BaseModel):
    rule_type: RuleType
    value: str
    action: ModerationAction
    active: bool = True


class ModerationRuleUpdate(BaseModel):
    value: str | None = None
    action: ModerationAction | None = None
    active: bool | None = None


class ModerationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_type: RuleType
    value: str
    action: ModerationAction
    active: bool
    created_at: datetime


# --- Bans ---

class BanCreate(BaseModel):
    user_id: UUID
    reason: str | None = None
    expires_at: datetime | None = None


class BanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    reason: str | None
    created_at: datetime
    expires_at: datetime | None
