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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CourseModel(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    topics: Mapped[list["TopicModel"]] = relationship(
        "TopicModel",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TopicModel.sequence",
    )
    reference_materials: Mapped[list["ReferenceMaterialModel"]] = relationship(
        "ReferenceMaterialModel",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        UniqueConstraint("tenant_id", "slug", name="uq_courses_tenant_slug"),
        Index("ix_courses_department_id", "department_id"),
        Index("ix_courses_tenant_id", "tenant_id"),
    )


class CurriculumVersionModel(Base):
    __tablename__ = "curriculum_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    programme_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("programmes.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("academic_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("academic_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    course_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            "programme_id", "version", name="uq_curriculum_programme_version"
        ),
        Index("ix_curriculum_programme_id", "programme_id"),
        Index("ix_curriculum_effective_session_id", "effective_session_id"),
    )


class TopicModel(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="primary")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
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

    course: Mapped["CourseModel"] = relationship(
        "CourseModel",
        back_populates="topics",
        overlaps="topics,reference_materials",
    )
    learning_outcomes: Mapped[list["LearningOutcomeModel"]] = relationship(
        "LearningOutcomeModel",
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LearningOutcomeModel.sequence",
    )

    __table_args__ = (
        UniqueConstraint("course_id", "sequence", name="uq_topic_course_sequence"),
        Index("ix_topics_course_id", "course_id"),
    )


class LearningOutcomeModel(Base):
    __tablename__ = "learning_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
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

    topic: Mapped["TopicModel"] = relationship(
        "TopicModel",
        back_populates="learning_outcomes",
        overlaps="learning_outcomes",
    )

    __table_args__ = (
        UniqueConstraint("topic_id", "sequence", name="uq_lo_topic_sequence"),
        Index("ix_learning_outcomes_topic_id", "topic_id"),
    )


class ReferenceMaterialModel(Base):
    __tablename__ = "reference_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    material_type: Mapped[str] = mapped_column(String(20), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
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

    course: Mapped["CourseModel"] = relationship(
        "CourseModel",
        back_populates="reference_materials",
        overlaps="topics,reference_materials",
    )

    __table_args__ = (Index("ix_reference_course_id", "course_id"),)


class CoursePrerequisiteModel(Base):
    __tablename__ = "course_prerequisites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    prerequisite_course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    prerequisite_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pre_requisite"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
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
            "course_id", "prerequisite_course_id", name="uq_course_prereq"
        ),
        Index("ix_prereq_course_id", "course_id"),
    )
