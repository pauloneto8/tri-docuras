"""transaction competence due payment dates

Revision ID: 012
Revises: 011
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("competence_date", sa.Date(), nullable=True))
    op.add_column("transactions", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("transactions", sa.Column("payment_date", sa.Date(), nullable=True))

    op.execute(
        """
        UPDATE transactions
        SET competence_date = transaction_date,
            due_date = transaction_date,
            payment_date = CASE WHEN status = 'actual' THEN transaction_date ELSE NULL END
        """
    )

    op.alter_column("transactions", "competence_date", nullable=False)
    op.alter_column("transactions", "due_date", nullable=False)

    op.create_check_constraint(
        "ck_transactions_planned_no_payment",
        "transactions",
        "(status = 'planned' AND payment_date IS NULL) OR (status = 'actual' AND payment_date IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_transactions_planned_no_payment", "transactions", type_="check")
    op.drop_column("transactions", "payment_date")
    op.drop_column("transactions", "due_date")
    op.drop_column("transactions", "competence_date")
