"""separate credit cards from accounts

Revision ID: 016
Revises: 015
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("institution", sa.String(length=100), nullable=True),
        sa.Column("credit_limit_cents", sa.BigInteger(), nullable=True),
        sa.Column("closing_day", sa.Integer(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("settlement_account_id", sa.Integer(), nullable=True),
        sa.Column("legacy_account_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["legacy_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["settlement_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_credit_card_user_name"),
        sa.CheckConstraint(
            "closing_day >= 1 AND closing_day <= 31",
            name="ck_credit_cards_closing_day",
        ),
        sa.CheckConstraint(
            "due_day >= 1 AND due_day <= 31",
            name="ck_credit_cards_due_day",
        ),
    )
    op.create_index("ix_credit_cards_user_id", "credit_cards", ["user_id"])

    op.execute(
        """
        INSERT INTO credit_cards (
            user_id, name, institution, credit_limit_cents,
            closing_day, due_day, legacy_account_id, is_active, created_at
        )
        SELECT
            user_id,
            name,
            institution,
            credit_limit_cents,
            COALESCE(closing_day, 1),
            COALESCE(due_day, 10),
            id,
            is_active,
            created_at
        FROM accounts
        WHERE account_type = 'cartao'
        """
    )

    op.add_column("card_invoices", sa.Column("card_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE card_invoices ci
        SET card_id = cc.id
        FROM credit_cards cc
        WHERE cc.legacy_account_id = ci.account_id
        """
    )
    op.drop_constraint("uq_card_invoices_account_due", "card_invoices", type_="unique")
    op.drop_index("ix_card_invoices_account_id", table_name="card_invoices")
    op.drop_constraint("card_invoices_account_id_fkey", "card_invoices", type_="foreignkey")
    op.drop_column("card_invoices", "account_id")
    op.alter_column("card_invoices", "card_id", nullable=False)
    op.create_foreign_key(
        "card_invoices_card_id_fkey",
        "card_invoices",
        "credit_cards",
        ["card_id"],
        ["id"],
    )
    op.create_index("ix_card_invoices_card_id", "card_invoices", ["card_id"])
    op.create_unique_constraint(
        "uq_card_invoices_card_due", "card_invoices", ["card_id", "due_date"]
    )

    op.add_column("transactions", sa.Column("card_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE transactions t
        SET card_id = cc.id,
            account_id = cc.settlement_account_id
        FROM credit_cards cc
        WHERE cc.legacy_account_id = t.account_id
        """
    )
    op.alter_column("transactions", "account_id", nullable=True)
    op.create_foreign_key(
        "fk_transactions_card_id",
        "transactions",
        "credit_cards",
        ["card_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_card_id", "transactions", ["card_id"])
    op.create_check_constraint(
        "ck_transactions_account_or_card",
        "transactions",
        "account_id IS NOT NULL OR card_id IS NOT NULL",
    )

    op.execute(
        """
        UPDATE accounts
        SET is_active = false
        WHERE account_type = 'cartao'
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_transactions_account_or_card", "transactions", type_="check")
    op.drop_index("ix_transactions_card_id", table_name="transactions")
    op.drop_constraint("fk_transactions_card_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "card_id")
    op.execute(
        """
        UPDATE transactions t
        SET account_id = cc.legacy_account_id
        FROM credit_cards cc
        WHERE t.card_id = cc.id AND t.account_id IS NULL
        """
    )
    op.alter_column("transactions", "account_id", nullable=False)

    op.add_column("card_invoices", sa.Column("account_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE card_invoices ci
        SET account_id = cc.legacy_account_id
        FROM credit_cards cc
        WHERE cc.id = ci.card_id
        """
    )
    op.drop_constraint("uq_card_invoices_card_due", "card_invoices", type_="unique")
    op.drop_index("ix_card_invoices_card_id", table_name="card_invoices")
    op.drop_constraint("card_invoices_card_id_fkey", "card_invoices", type_="foreignkey")
    op.drop_column("card_invoices", "card_id")
    op.alter_column("card_invoices", "account_id", nullable=False)
    op.create_foreign_key(
        "card_invoices_account_id_fkey",
        "card_invoices",
        "accounts",
        ["account_id"],
        ["id"],
    )
    op.create_index("ix_card_invoices_account_id", "card_invoices", ["account_id"])
    op.create_unique_constraint(
        "uq_card_invoices_account_due", "card_invoices", ["account_id", "due_date"]
    )

    op.execute(
        """
        UPDATE accounts a
        SET is_active = cc.is_active
        FROM credit_cards cc
        WHERE cc.legacy_account_id = a.id
        """
    )
    op.drop_index("ix_credit_cards_user_id", table_name="credit_cards")
    op.drop_table("credit_cards")
