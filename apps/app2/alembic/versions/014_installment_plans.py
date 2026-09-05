"""installment plans for parcelled transactions

Revision ID: 014
Revises: 013
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "installment_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
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
            "interval IN ('monthly', 'weekly', 'biweekly')",
            name="ck_installment_plans_interval",
        ),
        sa.CheckConstraint(
            "type IN ('expense', 'income')",
            name="ck_installment_plans_type",
        ),
        sa.CheckConstraint(
            "installment_count >= 2",
            name="ck_installment_plans_count",
        ),
    )
    op.create_index("ix_installment_plans_user_id", "installment_plans", ["user_id"])

    op.add_column(
        "transactions",
        sa.Column("installment_plan_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("installment_index", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_installment_plan_id",
        "transactions",
        "installment_plans",
        ["installment_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_transactions_installment_plan_id",
        "transactions",
        ["installment_plan_id"],
    )
    op.create_unique_constraint(
        "uq_transactions_installment_plan_index",
        "transactions",
        ["installment_plan_id", "installment_index"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transactions_installment_plan_index", "transactions", type_="unique"
    )
    op.drop_index("ix_transactions_installment_plan_id", table_name="transactions")
    op.drop_constraint(
        "fk_transactions_installment_plan_id", "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "installment_index")
    op.drop_column("transactions", "installment_plan_id")
    op.drop_index("ix_installment_plans_user_id", table_name="installment_plans")
    op.drop_table("installment_plans")
