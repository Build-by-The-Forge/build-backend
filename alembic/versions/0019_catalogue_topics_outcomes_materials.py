"""bring topics, learning_outcomes and reference_materials to the catalogue model

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-03 21:00:00.000000

Commit e70391d redesigned the catalogue (topics belong to a course, every
entity has status/updated_at, reference materials have a type) in the
domain, repositories and ORM models but added no migration, so on a
database built by migrations every catalogue query fails once a course
exists (docs/phase1-m2-schema-drift-investigation.md).

The old and new shapes are not interchangeable: an old topic hangs off a
curriculum version, an old reference material has no type, and an old
learning outcome hangs off an old topic. Rather than guess a conversion,
the upgrade refuses to run if any of the three tables has rows and
reports the counts; an operator decides what those rows mean. With the
tables empty it recreates them exactly as the models define them.

curriculum_versions and course_prerequisites are deliberately left
alone: no code path uses them and their final design is deferred to the
curriculum work.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

TABLES = ("learning_outcomes", "topics", "reference_materials")


def _refuse_if_populated(direction: str) -> None:
    bind = op.get_bind()
    counts = {
        table: bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        for table in TABLES
    }
    populated = {table: n for table, n in counts.items() if n}
    if populated:
        found = ", ".join(f"{table}={n}" for table, n in populated.items())
        raise RuntimeError(
            f"cannot {direction} 0019: these tables hold rows in the other "
            f"shape ({found}); convert or remove them explicitly first"
        )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    _refuse_if_populated("upgrade to")

    op.drop_index("ix_learning_outcomes_topic_id", table_name="learning_outcomes")
    op.drop_table("learning_outcomes")
    op.drop_index("ix_topics_curriculum_version_id", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_reference_course_id", table_name="reference_materials")
    op.drop_table("reference_materials")

    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "sequence", name="uq_topic_course_sequence"),
    )
    op.create_index("ix_topics_course_id", "topics", ["course_id"])

    op.create_table(
        "learning_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic_id", "sequence", name="uq_lo_topic_sequence"),
    )
    op.create_index("ix_learning_outcomes_topic_id", "learning_outcomes", ["topic_id"])

    op.create_table(
        "reference_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("material_type", sa.String(length=20), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reference_course_id", "reference_materials", ["course_id"])


def downgrade() -> None:
    """Recreate the 0005 shapes (empty tables only, as for the upgrade)."""
    _refuse_if_populated("downgrade from")

    op.drop_index("ix_learning_outcomes_topic_id", table_name="learning_outcomes")
    op.drop_table("learning_outcomes")
    op.drop_index("ix_topics_course_id", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_reference_course_id", table_name="reference_materials")
    op.drop_table("reference_materials")

    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"], ["curriculum_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "curriculum_version_id", "sequence", name="uq_topic_curriculum_sequence"
        ),
    )
    op.create_index(
        "ix_topics_curriculum_version_id", "topics", ["curriculum_version_id"]
    )

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

    op.create_table(
        "reference_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reference_course_id", "reference_materials", ["course_id"])
