"""transaction transfers

Revision ID: 010
Revises: 009
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("transfer_group_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("counterparty_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_counterparty_account",
        "transactions",
        "accounts",
        ["counterparty_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_transactions_transfer_group_id",
        "transactions",
        ["transfer_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_transfer_group_id", table_name="transactions")
    op.drop_constraint("fk_transactions_counterparty_account", "transactions", type_="foreignkey")
    op.drop_column("transactions", "counterparty_account_id")
    op.drop_column("transactions", "transfer_group_id")
