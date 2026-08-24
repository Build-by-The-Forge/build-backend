from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QuestionModel(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(String(36), nullable=False)
    learning_outcome_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    marks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    options: Mapped[list["QuestionOptionModel"]] = relationship(
        "QuestionOptionModel",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionOptionModel.display_order",
    )

    __table_args__ = (
        Index("ix_questions_tenant_id", "tenant_id"),
        Index("ix_questions_topic_id", "topic_id"),
        Index("ix_questions_learning_outcome_id", "learning_outcome_id"),
        Index("ix_questions_status", "status"),
    )


class QuestionOptionModel(Base):
    __tablename__ = "question_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped["QuestionModel"] = relationship(
        "QuestionModel",
        back_populates="options",
        overlaps="options",
    )

    __table_args__ = (
        UniqueConstraint("question_id", "display_order", name="uq_option_question_display_order"),
        Index("ix_option_question_id", "question_id"),
    )
