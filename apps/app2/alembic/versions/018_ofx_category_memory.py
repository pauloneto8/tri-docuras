"""ofx category memory and line category fields

Revision ID: 018
Revises: 017
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ofx_import_lines",
        sa.Column("suggested_category_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ofx_import_lines",
        sa.Column("chosen_category_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ofx_import_lines_suggested_category",
        "ofx_import_lines",
        "categories",
        ["suggested_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ofx_import_lines_chosen_category",
        "ofx_import_lines",
        "categories",
        ["chosen_category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "ofx_category_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("memo_key", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "memo_key", name="uq_ofx_category_memory_user_memo"),
    )
    op.create_index("ix_ofx_category_memory_user_id", "ofx_category_memory", ["user_id"])


def downgrade() -> None:
    op.drop_table("ofx_category_memory")
    op.drop_constraint(
        "fk_ofx_import_lines_chosen_category", "ofx_import_lines", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_ofx_import_lines_suggested_category", "ofx_import_lines", type_="foreignkey"
    )
    op.drop_column("ofx_import_lines", "chosen_category_id")
    op.drop_column("ofx_import_lines", "suggested_category_id")
