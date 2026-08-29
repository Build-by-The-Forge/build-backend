"""add attempt results and snapshot correct index

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_questions",
        sa.Column("correct_option_index", sa.Integer(), nullable=True),
    )
    op.create_table(
        "assessment_attempt_results",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("attempt_id", sa.String(length=255), nullable=False),
        sa.Column("assessment_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("breakdown_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["assessment_attempts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "attempt_id",
            name="uq_attempt_result_tenant_attempt",
        ),
    )
    op.create_index(
        "ix_attempt_results_tenant_id", "assessment_attempt_results", ["tenant_id"]
    )
    op.create_index(
        "ix_attempt_results_attempt_id", "assessment_attempt_results", ["attempt_id"]
    )
    op.create_index(
        "ix_attempt_results_assessment_id",
        "assessment_attempt_results",
        ["assessment_id"],
    )
    op.create_index(
        "ix_attempt_results_user_id", "assessment_attempt_results", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attempt_results_user_id", table_name="assessment_attempt_results")
    op.drop_index(
        "ix_attempt_results_assessment_id", table_name="assessment_attempt_results"
    )
    op.drop_index(
        "ix_attempt_results_attempt_id", table_name="assessment_attempt_results"
    )
    op.drop_index(
        "ix_attempt_results_tenant_id", table_name="assessment_attempt_results"
    )
    op.drop_table("assessment_attempt_results")
    op.drop_column("assessment_questions", "correct_option_index")
