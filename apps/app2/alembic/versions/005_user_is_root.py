"""user is_root flag

Revision ID: 005
Revises: 004
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_root", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE users SET is_root = true WHERE lower(email) = 'pauloneto8@gmail.com'"
    )


def downgrade() -> None:
    op.drop_column("users", "is_root")
