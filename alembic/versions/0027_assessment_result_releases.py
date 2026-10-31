"""staff release of an assessment's results

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-31 17:00:00.000000

One insert-only row per assessment: the primary key makes it single, and with
no update or delete path it can't be undone.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_result_releases",
        sa.Column("assessment_id", sa.String(255), sa.ForeignKey("assessments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", sa.String(255), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("released_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assessment_result_releases_tenant_id", "assessment_result_releases", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_result_releases_tenant_id", table_name="assessment_result_releases")
    op.drop_table("assessment_result_releases")
