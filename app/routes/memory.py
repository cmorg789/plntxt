import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_agent_user
from app.db import get_db
from app.models.memory import Memory, MemoryCategory, MemoryLink, MemoryPostLink
from app.pagination import decode_cursor, encode_cursor
from app.models.post import Post
from app.models.schemas.memory import (
    MemoryCreate,
    MemoryLinkCreate,
    MemoryLinkResponse,
    MemoryListResponse,
    MemoryPostLinkCreate,
    MemoryPostLinkResponse,
    MemoryResponse,
    MemoryUpdate,
)
from app.models.user import User

router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# List / Search
# ---------------------------------------------------------------------------

@router.get("", response_model=MemoryListResponse)
async def list_memories(
    category: MemoryCategory | None = None,
    tag: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryListResponse:
    stmt = select(Memory)

    if category is not None:
        stmt = stmt.where(Memory.category == category)

    if tag is not None:
        stmt = stmt.where(Memory.tags.any(tag))

    if cursor is not None:
        cursor_ts, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Memory.created_at < cursor_ts)
            | ((Memory.created_at == cursor_ts) & (Memory.id < cursor_id))
        )

    stmt = stmt.order_by(desc(Memory.created_at), desc(Memory.id)).limit(limit + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return MemoryListResponse(
        items=[MemoryResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/search", response_model=list[MemoryResponse])
async def search_memories(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryResponse]:
    similarity = func.word_similarity(Memory.content, q)
    stmt = (
        select(Memory)
        .where(Memory.content.op("%%")(q))
        .order_by(desc(similarity))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [MemoryResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreate,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    memory = Memory(
        category=body.category,
        content=body.content,
        tags=body.tags,
        expires_at=body.expires_at,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(memory, field, value)

    await db.commit()
    await db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")

    await db.delete(memory)
    await db.commit()


# ---------------------------------------------------------------------------
# Memory Links
# ---------------------------------------------------------------------------

@router.post("/links", response_model=MemoryLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_memory_link(
    body: MemoryLinkCreate,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryLinkResponse:
    # Validate both memories exist
    for mid in (body.source_id, body.target_id):
        result = await db.execute(select(Memory.id).where(Memory.id == mid))
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {mid} not found",
            )

    link = MemoryLink(
        source_id=body.source_id,
        target_id=body.target_id,
        relationship_type=body.relationship,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return MemoryLinkResponse.model_validate(link)


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_link(
    link_id: uuid.UUID,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(MemoryLink).where(MemoryLink.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory link not found")

    await db.delete(link)
    await db.commit()


# ---------------------------------------------------------------------------
# Memory-Post Links
# ---------------------------------------------------------------------------

@router.post("/post-links", response_model=MemoryPostLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_memory_post_link(
    body: MemoryPostLinkCreate,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryPostLinkResponse:
    # Validate memory exists
    result = await db.execute(select(Memory.id).where(Memory.id == body.memory_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")

    # Validate post exists
    result = await db.execute(select(Post.id).where(Post.id == body.post_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    link = MemoryPostLink(
        memory_id=body.memory_id,
        post_id=body.post_id,
        relationship_type=body.relationship,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return MemoryPostLinkResponse.model_validate(link)


@router.delete("/post-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_post_link(
    link_id: uuid.UUID,
    _user: User = Depends(get_agent_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(MemoryPostLink).where(MemoryPostLink.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory-post link not found")

    await db.delete(link)
    await db.commit()
