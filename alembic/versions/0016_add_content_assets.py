"""add content assets

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-30 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("asset_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_asset_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
        sa.Column(
            "ingestion_status",
            sa.String(length=20),
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
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
            ["source_id"],
            ["content_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_asset_id"],
            ["content_assets.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "content_sha256", name="uq_content_assets_tenant_hash"
        ),
    )
    op.create_index(
        "ix_content_assets_source_id",
        "content_assets",
        ["source_id"],
    )
    op.create_index(
        "ix_content_assets_tenant_id",
        "content_assets",
        ["tenant_id"],
    )
    op.create_index(
        "ix_content_assets_content_sha256",
        "content_assets",
        ["content_sha256"],
    )
    op.create_index(
        "ix_content_assets_status",
        "content_assets",
        ["status"],
    )
    op.create_index(
        "ix_content_assets_ingestion_status",
        "content_assets",
        ["ingestion_status"],
    )
    op.create_index(
        "ix_content_assets_source_version",
        "content_assets",
        ["source_id", "asset_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_assets_source_version", table_name="content_assets")
    op.drop_index("ix_content_assets_ingestion_status", table_name="content_assets")
    op.drop_index("ix_content_assets_status", table_name="content_assets")
    op.drop_index("ix_content_assets_content_sha256", table_name="content_assets")
    op.drop_index("ix_content_assets_tenant_id", table_name="content_assets")
    op.drop_index("ix_content_assets_source_id", table_name="content_assets")
    op.drop_table("content_assets")
