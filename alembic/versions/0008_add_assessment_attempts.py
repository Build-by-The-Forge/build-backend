"""add assessment attempts

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_attempts",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("assessment_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="in_progress"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_assessment_attempts_tenant_id", "assessment_attempts", ["tenant_id"]
    )
    op.create_index(
        "ix_assessment_attempts_assessment_id", "assessment_attempts", ["assessment_id"]
    )
    op.create_index(
        "ix_assessment_attempts_user_id", "assessment_attempts", ["user_id"]
    )
    op.create_index("ix_assessment_attempts_status", "assessment_attempts", ["status"])
    op.create_index(
        "uq_assessment_attempts_active",
        "assessment_attempts",
        ["tenant_id", "assessment_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
        sqlite_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("uq_assessment_attempts_active", table_name="assessment_attempts")
    op.drop_index("ix_assessment_attempts_status", table_name="assessment_attempts")
    op.drop_index("ix_assessment_attempts_user_id", table_name="assessment_attempts")
    op.drop_index(
        "ix_assessment_attempts_assessment_id", table_name="assessment_attempts"
    )
    op.drop_index("ix_assessment_attempts_tenant_id", table_name="assessment_attempts")
    op.drop_table("assessment_attempts")
