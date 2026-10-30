"""a fixed deadline on each assessment attempt

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-30 22:00:00.000000

Existing attempts get started_at + their assessment's current duration, the
only deadline they can be given. An attempt still in progress past that time
is expired from now on: it can be submitted, with the answers it has, but
takes no more. No attempt is changed in any other way.
"""

from datetime import timedelta

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    attempts = sa.table(
        "assessment_attempts",
        sa.column("id", sa.String),
        sa.column("assessment_id", sa.String),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    assessments = sa.table(
        "assessments",
        sa.column("id", sa.String),
        sa.column("duration_minutes", sa.Integer),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(attempts.c.id, attempts.c.started_at, assessments.c.duration_minutes).join(
            assessments, attempts.c.assessment_id == assessments.c.id
        )
    ).all()
    for attempt_id, started_at, duration_minutes in rows:
        bind.execute(
            attempts.update()
            .where(attempts.c.id == attempt_id)
            .values(expires_at=started_at + timedelta(minutes=duration_minutes))
        )

    with op.batch_alter_table("assessment_attempts") as batch:
        batch.alter_column("expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.drop_column("expires_at")
