"""agent insights (proactive Claude-generated financial insight per user/month)

Revision ID: 020
Revises: 019
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="claude-insight"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "year", "month", name="uq_agent_insight_user_period"),
    )
    op.create_index("ix_agent_insights_user_id", "agent_insights", ["user_id"])


def downgrade() -> None:
    op.drop_table("agent_insights")
