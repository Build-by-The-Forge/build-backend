"""S-02: the student's academic profile.

Revision ID: 0032
Revises: 0031

- ``academic_profiles``: one per membership, created by its first save. The
  programme and level it names belong to the profile's own tenant: every
  foreign key carries ``tenant_id``. Removing the membership removes the
  profile. A programme or level can't be deleted while a profile names it.
- ``academic_profile_courses``: the enrolled courses. A row's profile and
  course must both belong to the row's own tenant, so the profile key is
  composite, ``(profile_id, tenant_id)``, against ``unique (id, tenant_id)``.
  Deleting a course removes its enrolments.
- ``uq_programmes_tenant_id_id``: the programme key's target.

Nothing existing changes and no rows are written.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_programmes_tenant_id_id", "programmes", ["tenant_id", "id"])

    op.create_table(
        "academic_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("programme_id", sa.String(36), nullable=False),
        sa.Column("level_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_academic_profiles_tenant_user"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_academic_profiles_id_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_academic_profiles_membership",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "programme_id"],
            ["programmes.tenant_id", "programmes.id"],
            name="fk_academic_profiles_programme",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "level_code"],
            ["levels.tenant_id", "levels.code"],
            name="fk_academic_profiles_level",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "academic_profile_courses",
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("profile_id", "course_id", name="pk_academic_profile_courses"),
        sa.ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["academic_profiles.id", "academic_profiles.tenant_id"],
            name="fk_academic_profile_courses_profile",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            name="fk_academic_profile_courses_course",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_academic_profile_courses_tenant_course", "academic_profile_courses", ["tenant_id", "course_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_academic_profile_courses_tenant_course", table_name="academic_profile_courses")
    op.drop_table("academic_profile_courses")
    op.drop_table("academic_profiles")
    op.drop_constraint("uq_programmes_tenant_id_id", "programmes", type_="unique")
