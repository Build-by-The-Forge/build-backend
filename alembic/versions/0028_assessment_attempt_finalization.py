"""who finalized each attempt, and an index for finding expired ones

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-31 18:30:00.000000

Every attempt submitted so far was submitted by its student: nothing else could
finalize one until L1, and L1 hasn't been deployed.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.add_column(sa.Column("finalized_by", sa.String(20), nullable=True))
        batch.create_check_constraint("ck_assessment_attempts_finalized_by", "finalized_by IN ('student', 'deadline')")
    op.execute("UPDATE assessment_attempts SET finalized_by = 'student' WHERE status = 'submitted'")
    op.create_index(
        "ix_assessment_attempts_expired",
        "assessment_attempts",
        ["expires_at"],
        sqlite_where=sa.text("status = 'in_progress'"),
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("ix_assessment_attempts_expired", table_name="assessment_attempts")
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.drop_constraint("ck_assessment_attempts_finalized_by", type_="check")
        batch.drop_column("finalized_by")
