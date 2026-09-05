"""credit card invoices

Revision ID: 015
Revises: 014
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("credit_limit_cents", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column("closing_day", sa.Integer(), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column("due_day", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_accounts_closing_day",
        "accounts",
        "closing_day IS NULL OR (closing_day >= 1 AND closing_day <= 31)",
    )
    op.create_check_constraint(
        "ck_accounts_due_day",
        "accounts",
        "due_day IS NULL OR (due_day >= 1 AND due_day <= 31)",
    )

    op.create_table(
        "card_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        sa.Column("cycle_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("paid_from_account_id", sa.Integer(), nullable=True),
        sa.Column("payment_transfer_group_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["paid_from_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "due_date", name="uq_card_invoices_account_due"),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'paid')",
            name="ck_card_invoices_status",
        ),
    )
    op.create_index("ix_card_invoices_user_id", "card_invoices", ["user_id"])
    op.create_index("ix_card_invoices_account_id", "card_invoices", ["account_id"])

    op.add_column(
        "transactions",
        sa.Column("invoice_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_invoice_id",
        "transactions",
        "card_invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_invoice_id", "transactions", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_invoice_id", table_name="transactions")
    op.drop_constraint("fk_transactions_invoice_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "invoice_id")
    op.drop_index("ix_card_invoices_account_id", table_name="card_invoices")
    op.drop_index("ix_card_invoices_user_id", table_name="card_invoices")
    op.drop_table("card_invoices")
    op.drop_constraint("ck_accounts_due_day", "accounts", type_="check")
    op.drop_constraint("ck_accounts_closing_day", "accounts", type_="check")
    op.drop_column("accounts", "due_day")
    op.drop_column("accounts", "closing_day")
    op.drop_column("accounts", "credit_limit_cents")
