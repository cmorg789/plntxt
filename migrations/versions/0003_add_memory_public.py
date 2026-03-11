"""Add public column to memory table for knowledge graph visibility.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory",
        sa.Column("public", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    # Procedural memories are private by default
    op.execute("UPDATE memory SET public = false WHERE category = 'PROCEDURAL'")
    op.create_index("ix_memory_public_category", "memory", ["public", "category"])


def downgrade() -> None:
    op.drop_index("ix_memory_public_category", table_name="memory")
    op.drop_column("memory", "public")
