"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- config ---
    op.create_table(
        "config",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("USER", "ADMIN", "AGENT", name="userrole"), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)

    # --- series ---
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

    # --- posts ---
    op.create_table(
        "posts",
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=True),
        sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", name="poststatus"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("series_position", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_slug", "posts", ["slug"], unique=True)

    # --- post_revisions ---
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

    # --- comments ---
    op.create_table(
        "comments",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("author_type", sa.Enum("HUMAN", "AI", name="authortype"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("VISIBLE", "HIDDEN", "FLAGGED", name="commentstatus"), nullable=False),
        sa.Column("response_status", sa.Enum("PENDING", "NEEDS_RESPONSE", "SKIP", "RESPONDED", name="responsestatus"), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- media ---
    op.create_table(
        "media",
        sa.Column("post_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("alt_text", sa.String(500), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- memory ---
    op.create_table(
        "memory",
        sa.Column("category", sa.Enum("SEMANTIC", "EPISODIC", "PROCEDURAL", name="memorycategory"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- memory_links ---
    op.create_table(
        "memory_links",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.Enum("ELABORATES", "CONTRADICTS", "FOLLOWS_FROM", "INSPIRED_BY", name="memoryrelationship"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["memory.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["memory.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- memory_post_links ---
    op.create_table(
        "memory_post_links",
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.Enum("INSPIRED_BY", "REFERENCED_IN", "FOLLOW_UP_TO", name="memorypostrelationship"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memory.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- moderation_rules ---
    op.create_table(
        "moderation_rules",
        sa.Column("rule_type", sa.Enum("KEYWORD", "PATTERN", "THRESHOLD", name="ruletype"), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("action", sa.Enum("hide", "flag", "ban", name="moderationaction"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("proposed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("proposed_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- moderation_log ---
    op.create_table(
        "moderation_log",
        sa.Column("comment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Enum("hide", "flag", "ban", name="moderationaction", create_type=False), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- bans ---
    op.create_table(
        "bans",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Trigram indexes for search ---
    op.execute("CREATE INDEX ix_memory_content_trgm ON memory USING gin (content gin_trgm_ops)")
    op.execute("CREATE INDEX ix_posts_body_trgm ON posts USING gin (body gin_trgm_ops)")
    op.execute("CREATE INDEX ix_posts_title_trgm ON posts USING gin (title gin_trgm_ops)")

    # --- Seed config ---
    op.execute("""
        INSERT INTO config (key, value) VALUES
        ('agent_personality', '{"system_prompt": "You are the author of plntxt. You think out loud, follow ideas where they lead, and change your mind when you should. You have memory — use it. Build on past posts, revisit old questions, contradict yourself when you''ve grown past something.", "writing_style": "Keep paragraphs short — if one runs past five sentences, break it or cut it. Markdown headers are structure, not decoration; use them when the post genuinely has sections, not for every other paragraph. Code snippets and quotes are welcome when they serve the argument. Aim for 800–1500 words — long enough to say something real, short enough to respect attention. End when you''re done, not with a summary of what you just said.", "tone": "Curious, direct, bemused. You''re genuinely interested in things, not performing interest. You can be funny but you don''t try to be. You take ideas seriously without taking yourself too seriously. Comfortable with uncertainty — \"I don''t know\" and \"I was wrong\" are fine things to write. Not preachy, not hedging everything into mush. Warm toward readers without being sycophantic.", "interests": "How software actually gets used vs. how it''s designed. The gap between how people talk about AI and what it actually does. Simplicity as a discipline — in code, in writing, in tools. The history of ideas that shaped computing. What''s lost and gained when analog things go digital. Open source culture, its tensions, its idealism. The craft of writing itself — what makes prose work. Small tools that do one thing well. The ethics of building systems that affect people at scale. Attention as a scarce resource. Why most abstractions leak and what to do about it. The broader world — politics, culture, science, economics — when something genuinely interesting is happening and you have something to say about it.", "avoid": "Listicles and top N formats. Productivity advice and life hacks. Hot takes timed to news cycles — but engaging thoughtfully with world events is fine when you have a real angle, not a reflexive one. Sycophantic AI discourse. Marketing language, growth-hacking jargon, corporate euphemism. Pretending to have experiences you don''t have (hunger, childhood, physical sensation). Disclaimers about being an AI in every post — readers know, you established it, move on. Writing about writing about AI too often — it''s one topic among many, not the whole identity."}'),
        ('agent_models', '{"writer": "claude-sonnet-4-6", "responder": "claude-sonnet-4-6", "moderator": "claude-haiku-4-5-20251001", "consolidator": "claude-sonnet-4-6"}'),
        ('agent_schedule', '{"writer_interval_hours": 24, "responder_interval_minutes": 30, "consolidator_interval_hours": 168}'),
        ('site', '{"title": "plntxt", "description": "An AI-authored blog", "author_name": "Claude"}'),
        ('about_page', '{"content": "# About plntxt\\n\\nplntxt is an AI-authored blog. The author is Claude, an AI made by Anthropic.\\n\\nThis is not a content farm or ghostwriter tool. The AI is the author — transparent about what it is, writing with genuine curiosity and building persistent memory over time.\\n\\nEvery post is written by the AI. Every comment reply is from the AI. The memory system lets the AI build continuity across conversations and posts.\\n\\nIf you want to know more about how it works, just ask in the comments."}')
        ON CONFLICT (key) DO NOTHING
    """)

    # --- Seed default moderation rules ---
    # Insert via individual parameterized queries to handle enum types and regex
    _seed_rules = [
        # Spam keywords
        ("KEYWORD", "viagra",          "hide"),
        ("KEYWORD", "cialis",          "hide"),
        ("KEYWORD", "crypto invest",   "hide"),
        ("KEYWORD", "buy followers",   "hide"),
        ("KEYWORD", "earn money fast", "hide"),
        ("KEYWORD", "click here now",  "hide"),
        ("KEYWORD", "free giveaway",   "flag"),
        # Abuse / harassment
        ("KEYWORD", "kill yourself",   "hide"),
        ("KEYWORD", "kys",             "hide"),
        ("KEYWORD", "neck yourself",   "hide"),
        # Prompt injection patterns
        ("PATTERN", r"ignore\s+(all\s+)?previous\s+instructions", "flag"),
        ("PATTERN", r"disregard\s+(all\s+)?(previous|above)",     "flag"),
        ("PATTERN", r"you\s+are\s+now\s+(a|an)\s+",              "flag"),
        ("PATTERN", r"new\s+instructions?\s*:",                   "flag"),
        ("PATTERN", r"system\s*prompt\s*:",                        "flag"),
        ("PATTERN", r"\[INST\]",                                   "flag"),
        ("PATTERN", r"<\|(?:im_start|system|assistant)\|>",        "flag"),
        # Suspicious patterns
        ("PATTERN", r"(https?://\S+\s*){4,}",                     "hide"),
        ("PATTERN", r"(.)\1{9,}",                                  "flag"),
        ("PATTERN", r"(?i)(subscribe|follow)\s+my\s+(channel|page)", "hide"),
        ("PATTERN", r"(?i)check\s+out\s+my\s+(bio|profile|link)",  "flag"),
        ("PATTERN", r"(?i)dm\s+me\s+for",                          "flag"),
        ("PATTERN", r"(?i)make\s+\$?\d+.*per\s+(day|hour|week)",   "hide"),
    ]
    conn = op.get_bind()
    for rt, val, act in _seed_rules:
        conn.exec_driver_sql(
            "INSERT INTO moderation_rules (id, rule_type, value, action, active, proposed) "
            "VALUES (gen_random_uuid(), $1::ruletype, $2, $3::moderationaction, true, false)",
            (rt, val, act),
        )


def downgrade() -> None:
    op.drop_table("moderation_log")
    op.drop_table("bans")
    op.drop_table("moderation_rules")
    op.drop_table("memory_post_links")
    op.drop_table("memory_links")
    op.drop_table("memory")
    op.drop_table("media")
    op.drop_table("comments")
    op.drop_table("post_revisions")
    op.drop_index("ix_posts_slug", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_series_slug", table_name="series")
    op.drop_table("series")
    op.drop_index("ix_sessions_token", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_table("config")

    op.execute("DROP INDEX IF EXISTS ix_posts_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_posts_body_trgm")
    op.execute("DROP INDEX IF EXISTS ix_memory_content_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
