from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CurriculumSourceModel(Base):
    __tablename__ = "curriculum_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="official_benchmark")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    sync_frequency_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1.0")
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

    snapshots: Mapped[list["CurriculumSnapshotModel"]] = relationship(
        "CurriculumSnapshotModel",
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(CurriculumSnapshotModel.retrieved_at)",
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_curriculum_sources_code"),
        Index("ix_curriculum_sources_code", "code"),
        Index("ix_curriculum_sources_status", "status"),
    )


class CurriculumSnapshotModel(Base):
    __tablename__ = "curriculum_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="captured")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    source: Mapped["CurriculumSourceModel"] = relationship(
        "CurriculumSourceModel",
        back_populates="snapshots",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "content_sha256", name="uq_curriculum_snapshot_source_hash"),
        Index("ix_curriculum_snapshots_source_id", "source_id"),
        Index("ix_curriculum_snapshots_retrieved_at", "retrieved_at"),
        Index("ix_curriculum_snapshots_content_sha256", "content_sha256"),
    )
