"""add benchmark governance and audit

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add review_fingerprint column to benchmark_curricula
    with op.batch_alter_table("benchmark_curricula") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_fingerprint",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.create_index(
            "uq_benchmark_active_identity",
            ["discipline_group", "programme_code", "degree_level"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        )

    # 2. Create benchmark_audit_logs table
    op.create_table(
        "benchmark_audit_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("curriculum_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("diff_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_id"],
            ["benchmark_curricula.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_benchmark_audit_curriculum_created",
        "benchmark_audit_logs",
        ["curriculum_id", "created_at"],
    )
    op.create_index(
        "ix_benchmark_audit_action_created",
        "benchmark_audit_logs",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_benchmark_audit_action_created",
        table_name="benchmark_audit_logs",
    )
    op.drop_index(
        "ix_benchmark_audit_curriculum_created",
        table_name="benchmark_audit_logs",
    )
    op.drop_table("benchmark_audit_logs")

    with op.batch_alter_table("benchmark_curricula") as batch_op:
        batch_op.drop_index("uq_benchmark_active_identity")
        batch_op.drop_column("review_fingerprint")
