"""user onboarding flag

Revision ID: 007
Revises: 006
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE users u
        SET onboarding_completed = true
        WHERE EXISTS (SELECT 1 FROM accounts a WHERE a.user_id = u.id)
        """
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed")
