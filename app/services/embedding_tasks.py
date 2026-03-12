"""Background tasks for generating embeddings after a response is sent."""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.db import async_session
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_semaphore = asyncio.Semaphore(2)


async def _embed_in_thread(text: str) -> list[float]:
    """Run embed_text in a background thread, limited by semaphore."""
    async with _semaphore:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, embed_text, text)


async def generate_post_embedding(post_id: uuid.UUID) -> None:
    """Generate and store embedding for a post."""
    from app.models.post import Post

    async with async_session() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one_or_none()
        if post is None or not post.body:
            return
        try:
            post.embedding = await _embed_in_thread(post.body)
            await db.commit()
            logger.info("Generated embedding for post %s", post_id)
        except Exception:
            logger.exception("Failed to generate embedding for post %s", post_id)


async def generate_memory_embedding(memory_id: uuid.UUID) -> None:
    """Generate and store embedding for a memory."""
    from app.models.memory import Memory

    async with async_session() as db:
        result = await db.execute(select(Memory).where(Memory.id == memory_id))
        memory = result.scalar_one_or_none()
        if memory is None or not memory.content:
            return
        try:
            memory.embedding = await _embed_in_thread(memory.content)
            await db.commit()
            logger.info("Generated embedding for memory %s", memory_id)
        except Exception:
            logger.exception("Failed to generate embedding for memory %s", memory_id)
