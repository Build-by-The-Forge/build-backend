"""add faculty_id to programmes - sqlite compatible

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Inspect existing columns in programmes (Inspector is dialect-portable;
    # PRAGMA only exists on SQLite)
    cols = [col["name"] for col in sa.inspect(conn).get_columns("programmes")]

    # Add column if it does not exist
    if "faculty_id" not in cols:
        with op.batch_alter_table("programmes", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("faculty_id", sa.String(length=36), nullable=True)
            )

    # Backfill faculty_id from departments for existing rows (safe even if column already set)
    conn.execute(sa.text("""
        UPDATE programmes SET faculty_id = (
            SELECT faculty_id FROM departments WHERE departments.id = programmes.department_id
        ) WHERE faculty_id IS NULL
    """))

    # Ensure index exists
    indexes = [idx["name"] for idx in sa.inspect(conn).get_indexes("programmes")]
    if "ix_programmes_faculty_id" not in indexes:
        op.create_index("ix_programmes_faculty_id", "programmes", ["faculty_id"])

    # Make column NOT NULL and add FK (do in batch to support sqlite)
    with op.batch_alter_table("programmes", schema=None) as batch_op:
        batch_op.alter_column(
            "faculty_id", existing_type=sa.String(length=36), nullable=False
        )
        # create_foreign_key will be ignored on sqlite if it cannot be applied; create if not present
        fk_exists = any(
            fk["referred_table"] == "faculties" and "faculty_id" in fk["constrained_columns"]
            for fk in sa.inspect(conn).get_foreign_keys("programmes")
        )
        if not fk_exists:
            batch_op.create_foreign_key(
                "fk_programmes_faculty_id",
                "faculties",
                ["faculty_id"],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    with op.batch_alter_table("programmes", schema=None) as batch_op:
        batch_op.drop_constraint("fk_programmes_faculty_id", type_="foreignkey")
        batch_op.drop_index("ix_programmes_faculty_id")
        batch_op.drop_column("faculty_id")
