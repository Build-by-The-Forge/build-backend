"""add curriculum sources and snapshots

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curriculum_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=False),
        sa.Column(
            "source_type",
            sa.String(length=50),
            nullable=False,
            server_default="official_benchmark",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "sync_frequency_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column(
            "parser_version",
            sa.String(length=50),
            nullable=False,
            server_default="v1.0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_curriculum_sources_code"),
    )
    op.create_index("ix_curriculum_sources_code", "curriculum_sources", ["code"])
    op.create_index("ix_curriculum_sources_status", "curriculum_sources", ["status"])

    op.create_table(
        "curriculum_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_artifact_uri", sa.String(length=1024), nullable=False),
        sa.Column(
            "parser_version",
            sa.String(length=50),
            nullable=False,
            server_default="v1.0",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="captured",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["curriculum_sources.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "source_id",
            "content_sha256",
            name="uq_curriculum_snapshot_source_hash",
        ),
    )
    op.create_index(
        "ix_curriculum_snapshots_source_id",
        "curriculum_snapshots",
        ["source_id"],
    )
    op.create_index(
        "ix_curriculum_snapshots_retrieved_at",
        "curriculum_snapshots",
        ["retrieved_at"],
    )
    op.create_index(
        "ix_curriculum_snapshots_content_sha256",
        "curriculum_snapshots",
        ["content_sha256"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curriculum_snapshots_content_sha256", table_name="curriculum_snapshots"
    )
    op.drop_index(
        "ix_curriculum_snapshots_retrieved_at", table_name="curriculum_snapshots"
    )
    op.drop_index(
        "ix_curriculum_snapshots_source_id", table_name="curriculum_snapshots"
    )
    op.drop_table("curriculum_snapshots")
    op.drop_index("ix_curriculum_sources_status", table_name="curriculum_sources")
    op.drop_index("ix_curriculum_sources_code", table_name="curriculum_sources")
    op.drop_table("curriculum_sources")
