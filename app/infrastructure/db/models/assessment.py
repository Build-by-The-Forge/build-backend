from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QuestionModel(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
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
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
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


class AssessmentModel(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(255), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

    questions: Mapped[list["AssessmentQuestionModel"]] = relationship(
        "AssessmentQuestionModel",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentQuestionModel.sequence",
    )

    __table_args__ = (
        Index("ix_assessments_tenant_id", "tenant_id"),
        Index("ix_assessments_course_id", "course_id"),
        Index("ix_assessments_status", "status"),
    )


class AssessmentQuestionModel(Base):
    __tablename__ = "assessment_questions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_id: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    correct_option_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    assessment: Mapped["AssessmentModel"] = relationship(
        "AssessmentModel",
        back_populates="questions",
        overlaps="questions",
    )

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "question_id",
            name="uq_assessment_question",
        ),
        Index("ix_assessment_questions_assessment_id", "assessment_id"),
        Index("ix_assessment_questions_question_id", "question_id"),
    )


class AssessmentAttemptModel(Base):
    __tablename__ = "assessment_attempts"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(255), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    __table_args__ = (
        Index("ix_assessment_attempts_tenant_id", "tenant_id"),
        Index("ix_assessment_attempts_assessment_id", "assessment_id"),
        Index("ix_assessment_attempts_user_id", "user_id"),
        Index("ix_assessment_attempts_status", "status"),
        Index(
            "uq_assessment_attempts_active",
            "tenant_id",
            "assessment_id",
            "user_id",
            unique=True,
            sqlite_where=(status == "in_progress"),
            postgresql_where=(status == "in_progress"),
        ),
    )


class AttemptAnswerModel(Base):
    __tablename__ = "assessment_attempt_answers"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_question_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("assessment_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_option_index: Mapped[int] = mapped_column(Integer, nullable=False)
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

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "attempt_id",
            "assessment_question_id",
            name="uq_attempt_answer_question",
        ),
        Index("ix_attempt_answers_tenant_id", "tenant_id"),
        Index("ix_attempt_answers_attempt_id", "attempt_id"),
        Index("ix_attempt_answers_assessment_question_id", "assessment_question_id"),
    )


class AssessmentAttemptResultModel(Base):
    __tablename__ = "assessment_attempt_results"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
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

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "attempt_id",
            name="uq_attempt_result_tenant_attempt",
        ),
        Index("ix_attempt_results_tenant_id", "tenant_id"),
        Index("ix_attempt_results_attempt_id", "attempt_id"),
        Index("ix_attempt_results_assessment_id", "assessment_id"),
        Index("ix_attempt_results_user_id", "user_id"),
    )
