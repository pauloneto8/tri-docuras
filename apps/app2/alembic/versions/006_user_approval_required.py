"""require admin approval for user access

Revision ID: 006
Revises: 005
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_active = false WHERE is_root = false")
    op.alter_column(
        "users",
        "is_active",
        server_default=sa.false(),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "is_active",
        server_default=sa.true(),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
