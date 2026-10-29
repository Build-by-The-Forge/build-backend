"""durable dispatch claims for worker remote calls

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-29 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_ingestion_jobs", sa.Column("dispatch_claim_token", sa.String(length=36), nullable=True))
    op.add_column(
        "content_ingestion_jobs",
        sa.Column("dispatch_claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_content_ingestion_jobs_dispatch_claim",
        "content_ingestion_jobs",
        ["status", "dispatch_claim_expires_at", "created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("ix_content_ingestion_jobs_dispatch_claim", table_name="content_ingestion_jobs")
    op.drop_column("content_ingestion_jobs", "dispatch_claim_expires_at")
    op.drop_column("content_ingestion_jobs", "dispatch_claim_token")
