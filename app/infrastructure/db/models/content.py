from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
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

    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    faculty_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    programme_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("programmes.id", ondelete="SET NULL"), nullable=True
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    isbn_or_doi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    trust_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

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
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_sources.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
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
    ingestion_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="uploaded"
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

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

    source: Mapped[ContentSourceModel] = relationship(
        "ContentSourceModel", back_populates="assets"
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
