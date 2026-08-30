"""add content sources

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-30 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("authority_level", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("faculty_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("programme_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("isbn_or_doi", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("trust_policy", sa.JSON(), nullable=False),
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
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["faculty_id"],
            ["faculties.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["programmes.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_sources_code",
        "content_sources",
        ["code"],
    )
    op.create_index(
        "ix_content_sources_tenant_id",
        "content_sources",
        ["tenant_id"],
    )
    op.create_index(
        "ix_content_sources_source_type",
        "content_sources",
        ["source_type"],
    )
    op.create_index(
        "ix_content_sources_authority_level",
        "content_sources",
        ["authority_level"],
    )
    op.create_index(
        "ix_content_sources_status",
        "content_sources",
        ["status"],
    )
    op.create_index(
        "ix_content_sources_visibility",
        "content_sources",
        ["visibility"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_sources_visibility", table_name="content_sources")
    op.drop_index("ix_content_sources_status", table_name="content_sources")
    op.drop_index("ix_content_sources_authority_level", table_name="content_sources")
    op.drop_index("ix_content_sources_source_type", table_name="content_sources")
    op.drop_index("ix_content_sources_tenant_id", table_name="content_sources")
    op.drop_index("ix_content_sources_code", table_name="content_sources")
    op.drop_table("content_sources")
