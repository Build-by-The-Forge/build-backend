"""add content ingestion jobs

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-30 19:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_ingestion_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="uploaded"
        ),
        sa.Column("current_stage", sa.String(length=50), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=False),
        sa.Column(
            "is_retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("attempt_history", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("external_task_id", sa.String(length=100), nullable=True),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_callback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_event_ids", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["content_assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["content_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_ingestion_jobs_asset_id",
        "content_ingestion_jobs",
        ["asset_id"],
    )
    op.create_index(
        "ix_content_ingestion_jobs_source_id",
        "content_ingestion_jobs",
        ["source_id"],
    )
    op.create_index(
        "ix_content_ingestion_jobs_tenant_id",
        "content_ingestion_jobs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_content_ingestion_jobs_status",
        "content_ingestion_jobs",
        ["status"],
    )
    op.create_index(
        "ix_content_ingestion_jobs_pending_retry",
        "content_ingestion_jobs",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_content_ingestion_jobs_asset_created",
        "content_ingestion_jobs",
        ["asset_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_ingestion_jobs_asset_created", table_name="content_ingestion_jobs"
    )
    op.drop_index(
        "ix_content_ingestion_jobs_pending_retry", table_name="content_ingestion_jobs"
    )
    op.drop_index(
        "ix_content_ingestion_jobs_status", table_name="content_ingestion_jobs"
    )
    op.drop_index(
        "ix_content_ingestion_jobs_tenant_id", table_name="content_ingestion_jobs"
    )
    op.drop_index(
        "ix_content_ingestion_jobs_source_id", table_name="content_ingestion_jobs"
    )
    op.drop_index(
        "ix_content_ingestion_jobs_asset_id", table_name="content_ingestion_jobs"
    )
    op.drop_table("content_ingestion_jobs")
