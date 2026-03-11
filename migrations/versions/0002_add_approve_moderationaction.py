"""Fix moderationaction enum: rename lowercase values to uppercase names
and add APPROVE.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The original migration created moderationaction with lowercase values
    # (hide, flag, ban) but SQLAlchemy maps Python enums by name (HIDE, FLAG, BAN).
    # Rename existing values to uppercase and add APPROVE.
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'hide' TO 'HIDE'")
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'flag' TO 'FLAG'")
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'ban' TO 'BAN'")
    op.execute("ALTER TYPE moderationaction ADD VALUE IF NOT EXISTS 'APPROVE' BEFORE 'HIDE'")



def downgrade() -> None:
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'HIDE' TO 'hide'")
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'FLAG' TO 'flag'")
    op.execute("ALTER TYPE moderationaction RENAME VALUE 'BAN' TO 'ban'")
