from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContentSourceModel(Base):
    __tablename__ = "content_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    faculty_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True)
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    programme_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("programmes.id", ondelete="SET NULL"), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    isbn_or_doi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    trust_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)

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

    assets: Mapped[list[ContentAssetModel]] = relationship(
        "ContentAssetModel", back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_content_sources_code", "code"),
        Index("ix_content_sources_tenant_id", "tenant_id"),
        Index("ix_content_sources_source_type", "source_type"),
        Index("ix_content_sources_authority_level", "authority_level"),
        Index("ix_content_sources_status", "status"),
        Index("ix_content_sources_visibility", "visibility"),
    )


class ContentAssetModel(Base):
    __tablename__ = "content_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_sources.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    asset_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    ingestion_status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)

    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)

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

    source: Mapped[ContentSourceModel] = relationship("ContentSourceModel", back_populates="assets")
    jobs: Mapped[list[ContentIngestionJobModel]] = relationship(
        "ContentIngestionJobModel", back_populates="asset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_content_assets_source_id", "source_id"),
        Index("ix_content_assets_tenant_id", "tenant_id"),
        Index("ix_content_assets_content_sha256", "content_sha256"),
        Index("ix_content_assets_status", "status"),
        Index("ix_content_assets_ingestion_status", "ingestion_status"),
        Index("ix_content_assets_source_version", "source_id", "asset_version"),
        UniqueConstraint("tenant_id", "content_sha256", name="uq_content_assets_tenant_hash"),
    )


class ContentIngestionJobModel(Base):
    __tablename__ = "content_ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_sources.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    attempt_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)

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

    asset: Mapped[ContentAssetModel] = relationship("ContentAssetModel", back_populates="jobs")

    __table_args__ = (
        Index("ix_content_ingestion_jobs_asset_id", "asset_id"),
        Index("ix_content_ingestion_jobs_source_id", "source_id"),
        Index("ix_content_ingestion_jobs_tenant_id", "tenant_id"),
        Index("ix_content_ingestion_jobs_status", "status"),
        Index("ix_content_ingestion_jobs_pending_retry", "status", "next_retry_at"),
        Index("ix_content_ingestion_jobs_asset_created", "asset_id", "created_at"),
        # The ingestion worker's loops (P3-6 §11, migration 0024).
        Index(
            "ix_content_ingestion_jobs_worker_due",
            "status",
            "next_retry_at",
            "created_at",
            postgresql_where=text("status IN ('queued', 'failed', 'processing', 'extracted', 'chunked', 'indexed')"),
        ),
    )


class ContentIngestionEventModel(Base):
    """One row per logical AI-service callback the backend handled (M3-08)."""

    __tablename__ = "content_ingestion_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("content_ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_content_ingestion_events_job_id", "job_id"),)
