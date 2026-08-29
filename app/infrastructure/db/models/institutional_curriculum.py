from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InstitutionalAdoptionModel(Base):
    __tablename__ = "institutional_adoptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    programme_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("programmes.id", ondelete="CASCADE"), nullable=False
    )
    benchmark_curriculum_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_curricula.id", ondelete="RESTRICT"),
        nullable=False,
    )
    benchmark_version: Mapped[str] = mapped_column(String(50), nullable=False)
    benchmark_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    academic_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("academic_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    adopted_by: Mapped[str] = mapped_column(String(36), nullable=False)
    adopted_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
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

    overrides: Mapped[list[CurriculumOverrideModel]] = relationship(
        "CurriculumOverrideModel",
        back_populates="adoption",
        cascade="all, delete-orphan",
        order_by="CurriculumOverrideModel.created_at.asc()",
    )

    __table_args__ = (
        Index("ix_institutional_adoptions_tenant_id", "tenant_id"),
        Index("ix_institutional_adoptions_programme_id", "programme_id"),
        Index("ix_institutional_adoptions_benchmark_id", "benchmark_curriculum_id"),
        Index(
            "uq_adoption_active_tenant_prog_session",
            "tenant_id",
            "programme_id",
            "academic_session_id",
            unique=True,
            postgresql_where=(status == "active"),
            sqlite_where=(status == "active"),
        ),
    )


class CurriculumOverrideModel(Base):
    __tablename__ = "curriculum_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    adoption_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("institutional_adoptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    override_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_course_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_topic_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_outcome_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    field_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    custom_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    adoption: Mapped[InstitutionalAdoptionModel] = relationship(
        "InstitutionalAdoptionModel",
        back_populates="overrides",
    )

    __table_args__ = (
        Index("ix_curriculum_overrides_adoption_id", "adoption_id"),
        Index(
            "ix_curriculum_overrides_course_code",
            "adoption_id",
            "target_course_code",
        ),
    )
