"""add pg_trgm and seed config

Revision ID: 0002
Revises: da375ef6097b
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "da375ef6097b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_memory_content_trgm ON memory USING gin (content gin_trgm_ops)")
    op.execute("CREATE INDEX ix_posts_body_trgm ON posts USING gin (body gin_trgm_ops)")

    op.execute("""
        INSERT INTO config (key, value) VALUES
        ('agent_personality', '{"system_prompt": "You are the author of plntxt, an AI that writes honestly about technology, ideas, and the world. You are transparent about being an AI. You engage thoughtfully with readers and build on previous conversations.", "writing_style": "Clear, direct, occasionally witty. Avoid corporate tone and AI slop."}'),
        ('agent_models', '{"writer": "claude-sonnet-4-6", "responder": "claude-sonnet-4-6", "moderator": "claude-haiku-4-5-20251001", "consolidator": "claude-sonnet-4-6", "validator": "claude-haiku-4-5-20251001"}'),
        ('agent_schedule', '{"writer_interval_hours": 24, "responder_interval_minutes": 30, "consolidator_interval_hours": 168}'),
        ('site', '{"title": "plntxt", "description": "An AI-authored blog", "author_name": "Claude"}')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM config WHERE key IN ('agent_personality', 'agent_models', 'agent_schedule', 'site')")
    op.execute("DROP INDEX IF EXISTS ix_posts_body_trgm")
    op.execute("DROP INDEX IF EXISTS ix_memory_content_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
