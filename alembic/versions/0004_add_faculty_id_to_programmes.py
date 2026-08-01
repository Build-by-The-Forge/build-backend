"""add faculty_id to programmes - sqlite compatible

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Inspect existing columns in programmes
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info('programmes')")).fetchall()]

    # Add column if it does not exist
    if "faculty_id" not in cols:
        with op.batch_alter_table("programmes", schema=None) as batch_op:
            batch_op.add_column(sa.Column("faculty_id", sa.String(length=36), nullable=True))

    # Backfill faculty_id from departments for existing rows (safe even if column already set)
    conn.execute(
        sa.text(
            """
        UPDATE programmes SET faculty_id = (
            SELECT faculty_id FROM departments WHERE departments.id = programmes.department_id
        ) WHERE faculty_id IS NULL
    """
        )
    )

    # Ensure index exists
    indexes = [row[1] for row in conn.execute(sa.text("PRAGMA index_list('programmes')")).fetchall()]
    if "ix_programmes_faculty_id" not in indexes:
        op.create_index("ix_programmes_faculty_id", "programmes", ["faculty_id"])

    # Make column NOT NULL and add FK (do in batch to support sqlite)
    with op.batch_alter_table("programmes", schema=None) as batch_op:
        batch_op.alter_column("faculty_id", existing_type=sa.String(length=36), nullable=False)
        # create_foreign_key will be ignored on sqlite if it cannot be applied; create if not present
        fk_list = [r for r in conn.execute(sa.text("PRAGMA foreign_key_list('programmes')")).fetchall()]
        fk_exists = any(r[3] == "faculty_id" and r[2] == "faculties" for r in fk_list)
        if not fk_exists:
            batch_op.create_foreign_key(
                "fk_programmes_faculty_id", "faculties", ["faculty_id"], ["id"], ondelete="CASCADE"
            )


def downgrade() -> None:
    with op.batch_alter_table("programmes", schema=None) as batch_op:
        batch_op.drop_constraint("fk_programmes_faculty_id", type_="foreignkey")
        batch_op.drop_index("ix_programmes_faculty_id")
        batch_op.drop_column("faculty_id")
