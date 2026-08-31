"""multiusuario

Revision ID: 002
Revises: 001
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.execute("DELETE FROM budgets")
    op.execute("DELETE FROM transactions")
    op.execute("DELETE FROM categories")
    op.execute("DELETE FROM accounts")

    op.drop_constraint("uq_budget_category_period", "budgets", type_="unique")
    op.drop_constraint("categories_name_key", "categories", type_="unique")
    op.drop_constraint("accounts_name_key", "accounts", type_="unique")

    op.add_column("accounts", sa.Column("user_id", sa.Integer(), nullable=False))
    op.add_column("categories", sa.Column("user_id", sa.Integer(), nullable=False))
    op.add_column("transactions", sa.Column("user_id", sa.Integer(), nullable=False))
    op.add_column("budgets", sa.Column("user_id", sa.Integer(), nullable=False))

    op.create_foreign_key("fk_accounts_user_id", "accounts", "users", ["user_id"], ["id"])
    op.create_foreign_key("fk_categories_user_id", "categories", "users", ["user_id"], ["id"])
    op.create_foreign_key("fk_transactions_user_id", "transactions", "users", ["user_id"], ["id"])
    op.create_foreign_key("fk_budgets_user_id", "budgets", "users", ["user_id"], ["id"])

    op.create_unique_constraint("uq_account_user_name", "accounts", ["user_id", "name"])
    op.create_unique_constraint("uq_category_user_name", "categories", ["user_id", "name"])
    op.create_unique_constraint(
        "uq_budget_user_category_period", "budgets", ["user_id", "category_id", "year", "month"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_budget_user_category_period", "budgets", type_="unique")
    op.drop_constraint("uq_category_user_name", "categories", type_="unique")
    op.drop_constraint("uq_account_user_name", "accounts", type_="unique")

    op.drop_constraint("fk_budgets_user_id", "budgets", type_="foreignkey")
    op.drop_constraint("fk_transactions_user_id", "transactions", type_="foreignkey")
    op.drop_constraint("fk_categories_user_id", "categories", type_="foreignkey")
    op.drop_constraint("fk_accounts_user_id", "accounts", type_="foreignkey")

    op.drop_column("budgets", "user_id")
    op.drop_column("transactions", "user_id")
    op.drop_column("categories", "user_id")
    op.drop_column("accounts", "user_id")

    op.create_unique_constraint("accounts_name_key", "accounts", ["name"])
    op.create_unique_constraint("categories_name_key", "categories", ["name"])
    op.create_unique_constraint("uq_budget_category_period", "budgets", ["category_id", "year", "month"])

    op.drop_table("users")
