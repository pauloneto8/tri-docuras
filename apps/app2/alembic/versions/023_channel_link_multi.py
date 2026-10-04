"""allow one link per user+channel (telegram and whatsapp)

Revision ID: 023
Revises: 022
"""
from __future__ import annotations

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "user_channel_links_user_id_key", "user_channel_links", type_="unique"
    )
    op.create_unique_constraint(
        "uq_user_channel_link", "user_channel_links", ["user_id", "channel"]
    )
    op.create_index(
        "ix_user_channel_links_external",
        "user_channel_links",
        ["channel", "external_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_channel_links_external", table_name="user_channel_links")
    op.drop_constraint("uq_user_channel_link", "user_channel_links", type_="unique")
    op.create_unique_constraint(
        "user_channel_links_user_id_key", "user_channel_links", ["user_id"]
    )
