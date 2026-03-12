"""Add is_moderated and is_replied bools to comments

Revision ID: 0008
Revises: 0007
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("is_moderated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "comments",
        sa.Column("is_replied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("comments", "is_replied")
    op.drop_column("comments", "is_moderated")
