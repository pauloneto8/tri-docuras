"""account opening balance date

Revision ID: 008
Revises: 007
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("opening_balance_date", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE accounts
        SET opening_balance_date = created_at::date
        WHERE opening_balance_cents > 0
        """
    )


def downgrade() -> None:
    op.drop_column("accounts", "opening_balance_date")
