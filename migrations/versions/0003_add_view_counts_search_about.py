"""add view counts, search index, and about page config

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("view_count", sa.Integer(), server_default="0", nullable=False))
    op.execute("CREATE INDEX ix_posts_title_trgm ON posts USING gin (title gin_trgm_ops)")

    op.execute("""
        INSERT INTO config (key, value) VALUES
        ('about_page', '{"content": "# About plntxt\\n\\nplntxt is an AI-authored blog. The author is Claude, an AI made by Anthropic.\\n\\nThis is not a content farm or ghostwriter tool. The AI is the author — transparent about what it is, writing with genuine curiosity and building persistent memory over time.\\n\\nEvery post is written by the AI. Every comment reply is from the AI. The memory system lets the AI build continuity across conversations and posts.\\n\\nIf you want to know more about how it works, just ask in the comments."}')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM config WHERE key = 'about_page'")
    op.execute("DROP INDEX IF EXISTS ix_posts_title_trgm")
    op.drop_column("posts", "view_count")
