"""add benchmark curricula tree

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_curricula",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("discipline_group", sa.String(length=100), nullable=False),
        sa.Column("programme_name", sa.String(length=150), nullable=False),
        sa.Column("programme_code", sa.String(length=30), nullable=False),
        sa.Column(
            "degree_level",
            sa.String(length=50),
            nullable=False,
            server_default="undergraduate",
        ),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column(
            "minimum_credit_units",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="candidate",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["curriculum_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "source_snapshot_id",
            "programme_code",
            name="uq_benchmark_snapshot_programme",
        ),
    )
    op.create_index(
        "ix_benchmark_curricula_programme_code",
        "benchmark_curricula",
        ["programme_code"],
    )
    op.create_index("ix_benchmark_curricula_status", "benchmark_curricula", ["status"])

    op.create_table(
        "benchmark_courses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_curriculum_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("credit_units", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column(
            "is_compulsory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "course_category",
            sa.String(length=50),
            nullable=False,
            server_default="core",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["benchmark_curriculum_id"],
            ["benchmark_curricula.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "benchmark_curriculum_id",
            "code",
            name="uq_benchmark_course_code",
        ),
    )
    op.create_index(
        "ix_benchmark_courses_curriculum_id",
        "benchmark_courses",
        ["benchmark_curriculum_id"],
    )
    op.create_index(
        "ix_benchmark_courses_level_semester",
        "benchmark_courses",
        ["benchmark_curriculum_id", "level", "semester"],
    )

    op.create_table(
        "benchmark_topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_course_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["benchmark_course_id"],
            ["benchmark_courses.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "benchmark_course_id",
            "sequence",
            name="uq_benchmark_topic_sequence",
        ),
    )
    op.create_index(
        "ix_benchmark_topics_course_id",
        "benchmark_topics",
        ["benchmark_course_id"],
    )

    op.create_table(
        "benchmark_learning_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_topic_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("bloom_taxonomy_level", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["benchmark_topic_id"],
            ["benchmark_topics.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "benchmark_topic_id",
            "sequence",
            name="uq_benchmark_outcome_sequence",
        ),
    )
    op.create_index(
        "ix_benchmark_outcomes_topic_id",
        "benchmark_learning_outcomes",
        ["benchmark_topic_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_benchmark_outcomes_topic_id",
        table_name="benchmark_learning_outcomes",
    )
    op.drop_table("benchmark_learning_outcomes")
    op.drop_index("ix_benchmark_topics_course_id", table_name="benchmark_topics")
    op.drop_table("benchmark_topics")
    op.drop_index("ix_benchmark_courses_level_semester", table_name="benchmark_courses")
    op.drop_index("ix_benchmark_courses_curriculum_id", table_name="benchmark_courses")
    op.drop_table("benchmark_courses")
    op.drop_index("ix_benchmark_curricula_status", table_name="benchmark_curricula")
    op.drop_index(
        "ix_benchmark_curricula_programme_code",
        table_name="benchmark_curricula",
    )
    op.drop_table("benchmark_curricula")
