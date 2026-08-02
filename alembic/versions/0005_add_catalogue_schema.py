"""0005 add catalogue schema - courses, curriculum_versions, topics, learning_outcomes, reference_materials, course_prerequisites

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # courses
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("credit_units", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_courses_tenant_slug"),
    )
    op.create_index("ix_courses_department_id", "courses", ["department_id"])
    op.create_index("ix_courses_tenant_id", "courses", ["tenant_id"])

    # curriculum_versions
    op.create_table(
        "curriculum_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "version", name="uq_curriculum_course_version"),
    )
    op.create_index("ix_curriculum_course_id", "curriculum_versions", ["course_id"])

    # topics
    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["curriculum_version_id"], ["curriculum_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("curriculum_version_id", "sequence", name="uq_topic_curriculum_sequence"),
    )
    op.create_index("ix_topics_curriculum_version_id", "topics", ["curriculum_version_id"])

    # learning_outcomes
    op.create_table(
        "learning_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic_id", "sequence", name="uq_lo_topic_sequence"),
    )
    op.create_index("ix_learning_outcomes_topic_id", "learning_outcomes", ["topic_id"])

    # reference_materials
    op.create_table(
        "reference_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reference_course_id", "reference_materials", ["course_id"])

    # course_prerequisites
    op.create_table(
        "course_prerequisites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("prerequisite_course_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prerequisite_course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "prerequisite_course_id", name="uq_course_prereq"),
    )
    op.create_index("ix_prereq_course_id", "course_prerequisites", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_prereq_course_id", table_name="course_prerequisites")
    op.drop_table("course_prerequisites")
    op.drop_index("ix_reference_course_id", table_name="reference_materials")
    op.drop_table("reference_materials")
    op.drop_index("ix_learning_outcomes_topic_id", table_name="learning_outcomes")
    op.drop_table("learning_outcomes")
    op.drop_index("ix_topics_curriculum_version_id", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_curriculum_course_id", table_name="curriculum_versions")
    op.drop_table("curriculum_versions")
    op.drop_index("ix_courses_tenant_id", table_name="courses")
    op.drop_index("ix_courses_department_id", table_name="courses")
    op.drop_table("courses")
