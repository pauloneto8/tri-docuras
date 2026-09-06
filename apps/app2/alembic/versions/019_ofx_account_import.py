"""ofx import batches: support bank accounts

Revision ID: 019
Revises: 018
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ofx_import_batches",
        sa.Column("account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ofx_import_batches_account_id",
        "ofx_import_batches",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_ofx_import_batches_account_id",
        "ofx_import_batches",
        ["account_id"],
    )
    op.alter_column(
        "ofx_import_batches",
        "card_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_ofx_import_batches_card_xor_account",
        "ofx_import_batches",
        "(card_id IS NOT NULL AND account_id IS NULL) OR "
        "(card_id IS NULL AND account_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ofx_import_batches_card_xor_account",
        "ofx_import_batches",
        type_="check",
    )
    op.execute("DELETE FROM ofx_import_batches WHERE card_id IS NULL")
    op.alter_column(
        "ofx_import_batches",
        "card_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_index("ix_ofx_import_batches_account_id", table_name="ofx_import_batches")
    op.drop_constraint(
        "fk_ofx_import_batches_account_id",
        "ofx_import_batches",
        type_="foreignkey",
    )
    op.drop_column("ofx_import_batches", "account_id")
