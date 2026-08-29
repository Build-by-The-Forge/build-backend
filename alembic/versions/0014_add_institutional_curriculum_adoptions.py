"""add institutional curriculum adoptions and overrides

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-29 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institutional_adoptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("programme_id", sa.String(length=36), nullable=False),
        sa.Column("benchmark_curriculum_id", sa.String(length=36), nullable=False),
        sa.Column("benchmark_version", sa.String(length=50), nullable=False),
        sa.Column("benchmark_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("academic_session_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("adopted_by", sa.String(length=36), nullable=False),
        sa.Column("adopted_by_email", sa.String(length=255), nullable=False),
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
            ["programme_id"],
            ["programmes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_curriculum_id"],
            ["benchmark_curricula.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_session_id"],
            ["academic_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_institutional_adoptions_tenant_id",
        "institutional_adoptions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_institutional_adoptions_programme_id",
        "institutional_adoptions",
        ["programme_id"],
    )
    op.create_index(
        "ix_institutional_adoptions_benchmark_id",
        "institutional_adoptions",
        ["benchmark_curriculum_id"],
    )
    op.create_index(
        "uq_adoption_active_tenant_prog_session",
        "institutional_adoptions",
        ["tenant_id", "programme_id", "academic_session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "curriculum_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("adoption_id", sa.String(length=36), nullable=False),
        sa.Column("override_type", sa.String(length=30), nullable=False),
        sa.Column("target_course_code", sa.String(length=20), nullable=True),
        sa.Column("target_topic_id", sa.String(length=36), nullable=True),
        sa.Column("target_outcome_id", sa.String(length=36), nullable=True),
        sa.Column("field_overrides", sa.JSON(), nullable=True),
        sa.Column("custom_payload", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["adoption_id"],
            ["institutional_adoptions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_curriculum_overrides_adoption_id",
        "curriculum_overrides",
        ["adoption_id"],
    )
    op.create_index(
        "ix_curriculum_overrides_course_code",
        "curriculum_overrides",
        ["adoption_id", "target_course_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curriculum_overrides_course_code",
        table_name="curriculum_overrides",
    )
    op.drop_index(
        "ix_curriculum_overrides_adoption_id",
        table_name="curriculum_overrides",
    )
    op.drop_table("curriculum_overrides")

    op.drop_index(
        "uq_adoption_active_tenant_prog_session",
        table_name="institutional_adoptions",
    )
    op.drop_index(
        "ix_institutional_adoptions_benchmark_id",
        table_name="institutional_adoptions",
    )
    op.drop_index(
        "ix_institutional_adoptions_programme_id",
        table_name="institutional_adoptions",
    )
    op.drop_index(
        "ix_institutional_adoptions_tenant_id",
        table_name="institutional_adoptions",
    )
    op.drop_table("institutional_adoptions")
