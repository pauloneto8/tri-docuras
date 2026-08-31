"""recurring rules for fixed transactions

Revision ID: 013
Revises: 012
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("anchor_day", sa.Integer(), nullable=True),
        sa.Column("anchor_weekday", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly', 'monthly')",
            name="ck_recurring_rules_frequency",
        ),
        sa.CheckConstraint(
            "type IN ('expense', 'income')",
            name="ck_recurring_rules_type",
        ),
    )
    op.create_index("ix_recurring_rules_user_id", "recurring_rules", ["user_id"])

    op.add_column(
        "transactions",
        sa.Column("recurrence_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_recurrence_id",
        "transactions",
        "recurring_rules",
        ["recurrence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_recurrence_id", "transactions", ["recurrence_id"])
    op.create_unique_constraint(
        "uq_transactions_recurrence_due_date",
        "transactions",
        ["recurrence_id", "due_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_transactions_recurrence_due_date", "transactions", type_="unique")
    op.drop_index("ix_transactions_recurrence_id", table_name="transactions")
    op.drop_constraint("fk_transactions_recurrence_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "recurrence_id")
    op.drop_index("ix_recurring_rules_user_id", table_name="recurring_rules")
    op.drop_table("recurring_rules")
