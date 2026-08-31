"""planned transactions

Revision ID: 011
Revises: 010
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="actual",
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("source_planned_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_source_planned",
        "transactions",
        "transactions",
        ["source_planned_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_transactions_one_actual_per_planned
        ON transactions (source_planned_id)
        WHERE source_planned_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_transactions_one_actual_per_planned")
    op.drop_index("ix_transactions_status", table_name="transactions")
    op.drop_constraint("fk_transactions_source_planned", "transactions", type_="foreignkey")
    op.drop_column("transactions", "source_planned_id")
    op.drop_column("transactions", "status")
