"""The student's academic profile (S-02, migration 0032)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AcademicProfileModel(Base):
    __tablename__ = "academic_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    programme_id: Mapped[str] = mapped_column(String(36), nullable=False)
    level_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_academic_profiles_tenant_user"),
        UniqueConstraint("id", "tenant_id", name="uq_academic_profiles_id_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_academic_profiles_membership",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "programme_id"],
            ["programmes.tenant_id", "programmes.id"],
            name="fk_academic_profiles_programme",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "level_code"],
            ["levels.tenant_id", "levels.code"],
            name="fk_academic_profiles_level",
            ondelete="RESTRICT",
        ),
    )


class AcademicProfileCourseModel(Base):
    __tablename__ = "academic_profile_courses"

    profile_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    course_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("profile_id", "course_id", name="pk_academic_profile_courses"),
        ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["academic_profiles.id", "academic_profiles.tenant_id"],
            name="fk_academic_profile_courses_profile",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            name="fk_academic_profile_courses_course",
            ondelete="CASCADE",
        ),
        Index("ix_academic_profile_courses_tenant_course", "tenant_id", "course_id"),
    )
