"""add post series

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_series_slug", "series", ["slug"], unique=True)

    op.add_column("posts", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column("posts", sa.Column("series_position", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_posts_series_id", "posts", "series", ["series_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_posts_series_id", "posts", type_="foreignkey")
    op.drop_column("posts", "series_position")
    op.drop_column("posts", "series_id")
    op.drop_index("ix_series_slug", table_name="series")
    op.drop_table("series")
