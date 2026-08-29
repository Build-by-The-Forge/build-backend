"""0006 add assessment schema - questions and question_options.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # questions table
    op.create_table(
        "questions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("learning_outcome_id", sa.String(length=36), nullable=True),
        sa.Column("question_type", sa.String(length=20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column(
            "difficulty", sa.String(length=20), nullable=False, server_default="medium"
        ),
        sa.Column("marks", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="draft"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_questions_tenant_id", "questions", ["tenant_id"])
    op.create_index("ix_questions_topic_id", "questions", ["topic_id"])
    op.create_index(
        "ix_questions_learning_outcome_id", "questions", ["learning_outcome_id"]
    )
    op.create_index("ix_questions_status", "questions", ["status"])

    # question_options table
    op.create_table(
        "question_options",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "question_id", "display_order", name="uq_option_question_display_order"
        ),
    )
    op.create_index("ix_option_question_id", "question_options", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_option_question_id", table_name="question_options")
    op.drop_table("question_options")
    op.drop_index("ix_questions_status", table_name="questions")
    op.drop_index("ix_questions_learning_outcome_id", table_name="questions")
    op.drop_index("ix_questions_topic_id", table_name="questions")
    op.drop_index("ix_questions_tenant_id", table_name="questions")
    op.drop_table("questions")
