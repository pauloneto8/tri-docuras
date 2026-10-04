"""agent sessions and channel links"""
from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_chat_id", sa.String(length=255), nullable=True),
        sa.Column("pending_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )
    op.create_index("ix_agent_sessions_user_channel", "agent_sessions", ["user_id", "channel"])
    op.create_table(
        "user_channel_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("code", sa.String(length=16), nullable=True),
        sa.Column("code_expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )
    op.create_index("ix_user_channel_links_code", "user_channel_links", ["code"])


def downgrade() -> None:
    op.drop_index("ix_user_channel_links_code", table_name="user_channel_links")
    op.drop_table("user_channel_links")
    op.drop_index("ix_agent_sessions_user_channel", table_name="agent_sessions")
    op.drop_table("agent_sessions")
