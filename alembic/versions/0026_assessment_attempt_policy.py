"""an attempt policy on each assessment

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-31 15:00:00.000000

Existing assessments get the practice defaults, which match today's behaviour:
no limit, retakes on, immediate results and feedback, best attempt stands.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.add_column(sa.Column("attempt_kind", sa.String(20), nullable=False, server_default="practice"))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("retake_after_submission", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("result_visibility", sa.String(20), nullable=False, server_default="immediate"))
        batch.add_column(sa.Column("feedback_timing", sa.String(20), nullable=False, server_default="immediate"))
        batch.add_column(sa.Column("scoring_policy", sa.String(20), nullable=False, server_default="best"))
        batch.create_check_constraint("ck_assessments_attempt_kind", "attempt_kind IN ('practice', 'formal')")
        batch.create_check_constraint("ck_assessments_result_visibility", "result_visibility IN ('immediate', 'after_release')")
        batch.create_check_constraint(
            "ck_assessments_feedback_timing",
            "feedback_timing IN ('immediate', 'after_final_attempt', 'after_release', 'never')",
        )
        batch.create_check_constraint("ck_assessments_scoring_policy", "scoring_policy IN ('best', 'latest', 'first')")
        batch.create_check_constraint(
            "ck_assessments_attempt_limit",
            "(retake_after_submission AND (max_attempts IS NULL OR max_attempts > 1))"
            " OR (NOT retake_after_submission AND COALESCE(max_attempts, 0) = 1)",
        )
        batch.create_check_constraint(
            "ck_assessments_final_attempt_feedback",
            "feedback_timing <> 'after_final_attempt' OR max_attempts IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.drop_constraint("ck_assessments_final_attempt_feedback", type_="check")
        batch.drop_constraint("ck_assessments_attempt_limit", type_="check")
        batch.drop_constraint("ck_assessments_scoring_policy", type_="check")
        batch.drop_constraint("ck_assessments_feedback_timing", type_="check")
        batch.drop_constraint("ck_assessments_result_visibility", type_="check")
        batch.drop_constraint("ck_assessments_attempt_kind", type_="check")
        batch.drop_column("scoring_policy")
        batch.drop_column("feedback_timing")
        batch.drop_column("result_visibility")
        batch.drop_column("retake_after_submission")
        batch.drop_column("max_attempts")
        batch.drop_column("attempt_kind")
