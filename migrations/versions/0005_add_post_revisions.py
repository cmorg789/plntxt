"""add post revisions

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "post_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_post_revisions_post_id", "post_revisions", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_post_revisions_post_id", table_name="post_revisions")
    op.drop_table("post_revisions")
