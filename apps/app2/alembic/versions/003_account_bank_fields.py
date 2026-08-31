"""account bank fields

Revision ID: 003
Revises: 002
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("institution", sa.String(length=100), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("account_type", sa.String(length=20), nullable=False, server_default="corrente"),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "opening_balance_cents",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("UPDATE accounts SET account_type = 'carteira' WHERE name = 'Principal'")


def downgrade() -> None:
    op.drop_column("accounts", "opening_balance_cents")
    op.drop_column("accounts", "account_type")
    op.drop_column("accounts", "institution")
