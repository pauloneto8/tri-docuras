"""ofx fitid and import staging tables

Revision ID: 017
Revises: 016
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("ofx_fitid", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_transactions_ofx_fitid",
        "transactions",
        ["ofx_fitid"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_transactions_user_ofx_fitid
        ON transactions (user_id, ofx_fitid)
        WHERE ofx_fitid IS NOT NULL
        """
    )

    op.create_table(
        "ofx_import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ofx_import_batches_user_id", "ofx_import_batches", ["user_id"])
    op.create_index("ix_ofx_import_batches_card_id", "ofx_import_batches", ["card_id"])

    op.create_table(
        "ofx_import_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("fitid", sa.String(length=128), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("memo", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("suggested_action", sa.String(length=32), nullable=False),
        sa.Column("suggested_transaction_id", sa.Integer(), nullable=True),
        sa.Column("suggested_invoice_id", sa.Integer(), nullable=True),
        sa.Column("chosen_action", sa.String(length=32), nullable=True),
        sa.Column("chosen_transaction_id", sa.Integer(), nullable=True),
        sa.Column("chosen_invoice_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["ofx_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["suggested_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_invoice_id"], ["card_invoices.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["chosen_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["chosen_invoice_id"], ["card_invoices.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ofx_import_lines_batch_id", "ofx_import_lines", ["batch_id"])


def downgrade() -> None:
    op.drop_table("ofx_import_lines")
    op.drop_table("ofx_import_batches")
    op.execute("DROP INDEX IF EXISTS uq_transactions_user_ofx_fitid")
    op.drop_index("ix_transactions_ofx_fitid", table_name="transactions")
    op.drop_column("transactions", "ofx_fitid")
