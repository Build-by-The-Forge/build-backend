"""add attempt answers

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_attempt_answers",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("attempt_id", sa.String(length=255), nullable=False),
        sa.Column("assessment_question_id", sa.String(length=255), nullable=False),
        sa.Column("selected_option_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["assessment_attempts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assessment_question_id"],
            ["assessment_questions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "attempt_id",
            "assessment_question_id",
            name="uq_attempt_answer_question",
        ),
    )
    op.create_index(
        "ix_attempt_answers_tenant_id", "assessment_attempt_answers", ["tenant_id"]
    )
    op.create_index(
        "ix_attempt_answers_attempt_id", "assessment_attempt_answers", ["attempt_id"]
    )
    op.create_index(
        "ix_attempt_answers_assessment_question_id",
        "assessment_attempt_answers",
        ["assessment_question_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attempt_answers_assessment_question_id",
        table_name="assessment_attempt_answers",
    )
    op.drop_index(
        "ix_attempt_answers_attempt_id", table_name="assessment_attempt_answers"
    )
    op.drop_index(
        "ix_attempt_answers_tenant_id", table_name="assessment_attempt_answers"
    )
    op.drop_table("assessment_attempt_answers")
