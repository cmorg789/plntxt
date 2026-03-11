"""add pgvector embeddings to memory and posts

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 256-d vectors (nomic-embed-text-v1.5 with Matryoshka truncation)
    op.execute("ALTER TABLE memory ADD COLUMN embedding vector(256)")
    op.execute("ALTER TABLE posts ADD COLUMN embedding vector(256)")

    # HNSW indexes for cosine distance — good default for normalized embeddings
    op.execute(
        "CREATE INDEX ix_memory_embedding_hnsw ON memory "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_posts_embedding_hnsw ON posts "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memory_embedding_hnsw")
    op.execute("ALTER TABLE posts DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE memory DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
