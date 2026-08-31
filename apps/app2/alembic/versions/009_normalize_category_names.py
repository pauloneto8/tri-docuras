"""normalize category names

Revision ID: 009
Revises: 008
Create Date: 2026-08-30
"""

from pathlib import Path
import sys
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.services.text_correction import correct_category_name

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, user_id, name FROM categories")).fetchall()
    for row in rows:
        cat_id, user_id, name = row
        fixed = correct_category_name(name)
        if fixed == name:
            continue
        conflict = connection.execute(
            sa.text(
                "SELECT id FROM categories "
                "WHERE user_id = :user_id AND name = :name AND id != :id"
            ),
            {"user_id": user_id, "name": fixed, "id": cat_id},
        ).first()
        if conflict:
            continue
        connection.execute(
            sa.text("UPDATE categories SET name = :name WHERE id = :id"),
            {"name": fixed, "id": cat_id},
        )


def downgrade() -> None:
    pass
