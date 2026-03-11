"""add email config key

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-11
"""
import json
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO config (key, value) VALUES ('email', %s) ON CONFLICT (key) DO NOTHING"
        % repr(json.dumps({
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "",
            "smtp_from": "noreply@plntxt.dev",
            "use_tls": True,
            "verification_token_expire_hours": 48,
        }))
    )


def downgrade() -> None:
    op.execute("DELETE FROM config WHERE key = 'email'")
