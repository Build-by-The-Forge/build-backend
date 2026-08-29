from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BenchmarkCurriculumModel(Base):
    __tablename__ = "benchmark_curricula"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    discipline_group: Mapped[str] = mapped_column(String(100), nullable=False)
    programme_name: Mapped[str] = mapped_column(String(150), nullable=False)
    programme_code: Mapped[str] = mapped_column(String(30), nullable=False)
    degree_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="undergraduate"
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    minimum_credit_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=120
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    review_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
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

    courses: Mapped[list["BenchmarkCourseModel"]] = relationship(
        "BenchmarkCourseModel",
        back_populates="curriculum",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BenchmarkCourseModel.sequence",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id",
            "programme_code",
            name="uq_benchmark_snapshot_programme",
        ),
        Index("ix_benchmark_curricula_programme_code", "programme_code"),
        Index("ix_benchmark_curricula_status", "status"),
        Index(
            "uq_benchmark_active_identity",
            "discipline_group",
            "programme_code",
            "degree_level",
            unique=True,
            postgresql_where=(status == "active"),
            sqlite_where=(status == "active"),
        ),
    )


class BenchmarkCourseModel(Base):
    __tablename__ = "benchmark_courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benchmark_curriculum_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_curricula.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    is_compulsory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    course_category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="core"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    curriculum: Mapped["BenchmarkCurriculumModel"] = relationship(
        "BenchmarkCurriculumModel",
        back_populates="courses",
    )
    topics: Mapped[list["BenchmarkTopicModel"]] = relationship(
        "BenchmarkTopicModel",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BenchmarkTopicModel.sequence",
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_curriculum_id",
            "code",
            name="uq_benchmark_course_code",
        ),
        Index(
            "ix_benchmark_courses_curriculum_id",
            "benchmark_curriculum_id",
        ),
        Index(
            "ix_benchmark_courses_level_semester",
            "benchmark_curriculum_id",
            "level",
            "semester",
        ),
    )


class BenchmarkTopicModel(Base):
    __tablename__ = "benchmark_topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benchmark_course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    course: Mapped["BenchmarkCourseModel"] = relationship(
        "BenchmarkCourseModel",
        back_populates="topics",
    )
    outcomes: Mapped[list["BenchmarkLearningOutcomeModel"]] = relationship(
        "BenchmarkLearningOutcomeModel",
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BenchmarkLearningOutcomeModel.sequence",
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_course_id",
            "sequence",
            name="uq_benchmark_topic_sequence",
        ),
        Index("ix_benchmark_topics_course_id", "benchmark_course_id"),
    )


class BenchmarkLearningOutcomeModel(Base):
    __tablename__ = "benchmark_learning_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benchmark_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    bloom_taxonomy_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    topic: Mapped["BenchmarkTopicModel"] = relationship(
        "BenchmarkTopicModel",
        back_populates="outcomes",
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_topic_id",
            "sequence",
            name="uq_benchmark_outcome_sequence",
        ),
        Index("ix_benchmark_outcomes_topic_id", "benchmark_topic_id"),
    )
