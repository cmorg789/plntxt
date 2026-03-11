"""Backfill embeddings for existing memory and post rows.

Usage:
    python -m scripts.backfill_embeddings
"""

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.memory import Memory
from app.models.post import Post
from app.services.embeddings import embed_texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 64


async def backfill_memories(session: AsyncSession) -> int:
    count = 0
    while True:
        result = await session.execute(
            select(Memory)
            .where(Memory.embedding.is_(None))
            .order_by(Memory.created_at)
            .limit(BATCH_SIZE)
        )
        rows = list(result.scalars().all())
        if not rows:
            break

        texts = [r.content for r in rows]
        embeddings = embed_texts(texts)

        for row, emb in zip(rows, embeddings):
            await session.execute(
                update(Memory).where(Memory.id == row.id).values(embedding=emb)
            )

        await session.commit()
        count += len(rows)
        logger.info("Backfilled %d memories (total: %d)", len(rows), count)

    return count


async def backfill_posts(session: AsyncSession) -> int:
    count = 0
    while True:
        result = await session.execute(
            select(Post)
            .where(Post.embedding.is_(None))
            .order_by(Post.created_at)
            .limit(BATCH_SIZE)
        )
        rows = list(result.scalars().all())
        if not rows:
            break

        texts = [r.body for r in rows]
        embeddings = embed_texts(texts)

        for row, emb in zip(rows, embeddings):
            await session.execute(
                update(Post).where(Post.id == row.id).values(embedding=emb)
            )

        await session.commit()
        count += len(rows)
        logger.info("Backfilled %d posts (total: %d)", len(rows), count)

    return count


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        mem_count = await backfill_memories(session)
        logger.info("Memory backfill complete: %d rows", mem_count)

        post_count = await backfill_posts(session)
        logger.info("Posts backfill complete: %d rows", post_count)

    await engine.dispose()
    logger.info("Done. Backfilled %d total rows.", mem_count + post_count)


if __name__ == "__main__":
    asyncio.run(main())
