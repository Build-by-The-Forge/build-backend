from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
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
    # A student's personal source (M3-D): set exactly when visibility is private.
    owner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

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
        CheckConstraint("(visibility = 'private') = (owner_user_id IS NOT NULL)", name="ck_content_sources_owner"),
        Index(
            "ux_content_sources_personal",
            "tenant_id",
            "owner_user_id",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
            sqlite_where=text("owner_user_id IS NOT NULL"),
        ),
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
    # M3-D (migration 0030). Every document from before it is unclassified.
    ownership_class: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unclassified", server_default="unclassified"
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    blob_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trust_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The shelf form (contract #87).
    course_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    semester: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

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
        UniqueConstraint("tenant_id", "id", name="uq_content_assets_tenant_id_id"),
        # Two partial indexes replace the tenant-wide one (M3-D): deduplicating
        # bytes never merges ownership, and a deleted document holds no hash.
        Index(
            "ux_content_assets_shared_hash",
            "tenant_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("ownership_class <> 'personal' AND status <> 'deleted'"),
            sqlite_where=text("ownership_class <> 'personal' AND status <> 'deleted'"),
        ),
        Index(
            "ux_content_assets_personal_hash",
            "tenant_id",
            "owner_user_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("ownership_class = 'personal' AND status <> 'deleted'"),
            sqlite_where=text("ownership_class = 'personal' AND status <> 'deleted'"),
        ),
        Index(
            "ix_content_assets_owner",
            "tenant_id",
            "owner_user_id",
            postgresql_where=text("owner_user_id IS NOT NULL"),
            sqlite_where=text("owner_user_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["tenant_id", "blob_id"],
            ["content_blobs.tenant_id", "content_blobs.id"],
            name="fk_content_assets_blob",
            ondelete="RESTRICT",
        ),
        # SET NULL with a column list (PostgreSQL 15+) keeps the tenant when a course
        # goes. SQLite, which the unit tests build from these models, has no column
        # list, so the constraint exists on PostgreSQL only.
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            name="fk_content_assets_course",
            ondelete="SET NULL (course_id)",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "ownership_class IN ('institutional', 'personal', 'unclassified')", name="ck_content_assets_ownership_class"
        ),
        CheckConstraint("(ownership_class = 'personal') = (owner_user_id IS NOT NULL)", name="ck_content_assets_owner"),
        CheckConstraint("blob_id IS NULL OR tenant_id IS NOT NULL", name="ck_content_assets_blob_tenant"),
        CheckConstraint("course_id IS NULL OR tenant_id IS NOT NULL", name="ck_content_assets_course_tenant"),
        CheckConstraint(
            "trust_class IS NULL OR trust_class IN ('user_provided', 'staff_provided')", name="ck_content_assets_trust_class"
        ),
        CheckConstraint("level IS NULL OR level IN (100, 200, 300, 400, 500, 600)", name="ck_content_assets_level"),
        CheckConstraint("semester IS NULL OR semester BETWEEN 1 AND 3", name="ck_content_assets_semester"),
        CheckConstraint(
            "document_type IS NULL OR document_type IN"
            " ('lecture_notes', 'summary', 'assignment', 'project_report', 'slides', 'other')",
            name="ck_content_assets_document_type",
        ),
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
        # One active job per asset (M3-D migration 0030).
        Index(
            "ux_content_ingestion_jobs_active_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("status NOT IN ('ready', 'failed')"),
            sqlite_where=text("status NOT IN ('ready', 'failed')"),
        ),
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


# --- M3-D, migration 0030 (docs/m3-d-migration-0030.md) --------------------------------

_OWNERSHIP = "('institutional', 'personal', 'unclassified')"


def _asset_reference(name: str, ondelete: str = "CASCADE") -> ForeignKeyConstraint:
    """A tenant-consistent reference to a document."""
    return ForeignKeyConstraint(
        ["tenant_id", "asset_id"], ["content_assets.tenant_id", "content_assets.id"], name=name, ondelete=ondelete
    )


class ContentBlobModel(Base):
    """Physical bytes, shared by documents with the same hash, holding no person,
    consent or permission. At most one row per hash isn't deleting."""

    __tablename__ = "content_blobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    generation: Mapped[str] = mapped_column(String(36), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_content_blobs_tenant_id_id"),
        UniqueConstraint("object_key", name="uq_content_blobs_object_key"),
        # A PostgreSQL regex; SQLite, used by the unit tests, has no ~ operator.
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_content_blobs_sha256").ddl_if(dialect="postgresql"),
        CheckConstraint("size_bytes > 0", name="ck_content_blobs_size"),
        CheckConstraint("state IN ('pending', 'active', 'deleting')", name="ck_content_blobs_state"),
        CheckConstraint("state <> 'pending' OR claimed_until IS NOT NULL", name="ck_content_blobs_pending_claim"),
        CheckConstraint("state <> 'active' OR claimed_until IS NULL", name="ck_content_blobs_active_claim"),
        Index(
            "ux_content_blobs_live_hash",
            "tenant_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("state <> 'deleting'"),
            sqlite_where=text("state <> 'deleting'"),
        ),
        Index("ix_content_blobs_sweep", "state", "claimed_until"),
    )


class ContentOwnershipClassificationModel(Base):
    """Append-only: each recorded decision on a document's ownership class."""

    __tablename__ = "content_ownership_classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_class: Mapped[str] = mapped_column(String(20), nullable=False)
    new_class: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_via: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        _asset_reference("fk_content_classifications_asset"),
        CheckConstraint(f"previous_class IN {_OWNERSHIP}", name="ck_content_classifications_previous"),
        CheckConstraint(f"new_class IN {_OWNERSHIP}", name="ck_content_classifications_new"),
        CheckConstraint("new_class <> previous_class", name="ck_content_classifications_change"),
        CheckConstraint("decided_via IN ('operator_command', 'staff_route')", name="ck_content_classifications_via"),
        CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_content_classifications_evidence"),
        CheckConstraint("decided_via <> 'operator_command' OR run_id IS NOT NULL", name="ck_content_classifications_run"),
        Index("ix_content_classifications_asset", "tenant_id", "asset_id", text("decided_at DESC")),
    )


class ContentScanModel(Base):
    """One scan per document, never shared across identical bytes, with a fenced verdict."""

    __tablename__ = "content_scans"

    asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    verdict: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    fence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scanner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signature_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        _asset_reference("fk_content_scans_asset"),
        CheckConstraint("verdict IN ('pending', 'accepted', 'rejected')", name="ck_content_scans_verdict"),
        CheckConstraint("fence >= 0", name="ck_content_scans_fence"),
        CheckConstraint("attempts >= 0", name="ck_content_scans_attempts"),
        CheckConstraint(
            "verdict = 'pending' OR (scanner IS NOT NULL AND signature_version IS NOT NULL AND scanned_at IS NOT NULL)",
            name="ck_content_scans_recorded",
        ),
        Index(
            "ix_content_scans_due",
            "next_attempt_at",
            postgresql_where=text("verdict = 'pending'"),
            sqlite_where=text("verdict = 'pending'"),
        ),
        Index(
            "ix_content_scans_rescan",
            "signature_version",
            postgresql_where=text("verdict = 'accepted'"),
            sqlite_where=text("verdict = 'accepted'"),
        ),
    )


class ContentRightsAssertionModel(Base):
    """Append-only: each owner declaration or staff review of one document's rights."""

    __tablename__ = "content_rights_assertions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    asserted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    rights_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    redistribution: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_use: Mapped[str] = mapped_column(String(20), nullable=False, default="not_permitted", server_default="not_permitted")
    declaration_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    asserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        _asset_reference("fk_content_rights_asset"),
        UniqueConstraint("tenant_id", "asset_id", "id", name="uq_content_rights_tenant_asset_id"),
        CheckConstraint("kind IN ('owner_declaration', 'staff_review', 'copied_source_default')", name="ck_content_rights_kind"),
        CheckConstraint(
            "rights_basis IN ('own_work', 'lecturer_provided', 'institution_licensed', 'publisher_licensed',"
            " 'public_domain', 'unknown')",
            name="ck_content_rights_basis",
        ),
        CheckConstraint(
            "audience IN ('owner', 'tenant', 'faculty', 'department', 'programme', 'course')", name="ck_content_rights_audience"
        ),
        CheckConstraint("redistribution IN ('none', 'tenant_only', 'permitted')", name="ck_content_rights_redistribution"),
        CheckConstraint("ai_use IN ('not_permitted', 'permitted')", name="ck_content_rights_ai_use"),
        CheckConstraint(
            "kind <> 'owner_declaration' OR (declaration_version IS NOT NULL AND length(trim(declaration_version)) > 0)",
            name="ck_content_rights_declaration_version",
        ),
        CheckConstraint(
            "kind <> 'staff_review' OR (outcome IS NOT NULL AND outcome IN ('accepted', 'rejected')"
            " AND reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_content_rights_review",
        ),
        CheckConstraint("kind = 'staff_review' OR outcome IS NULL", name="ck_content_rights_outcome_only_review"),
        Index("ix_content_rights_asset", "tenant_id", "asset_id", text("asserted_at DESC")),
    )


class ContentPublicationModel(Base):
    """One row per publication request. The consent never changes; only its end
    is recorded, once, under the transition rules the migration's trigger enforces."""

    __tablename__ = "content_publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    declaration_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="requested", server_default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        _asset_reference("fk_content_publications_asset"),
        ForeignKeyConstraint(
            ["tenant_id", "asset_id", "declaration_id"],
            [
                "content_rights_assertions.tenant_id",
                "content_rights_assertions.asset_id",
                "content_rights_assertions.id",
            ],
            name="fk_content_publications_declaration",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(trim(consent_version)) > 0", name="ck_content_publications_consent"),
        CheckConstraint(
            "state IN ('requested', 'published', 'withdrawn', 'taken_down', 'closed')", name="ck_content_publications_state"
        ),
        CheckConstraint(
            "state NOT IN ('published', 'taken_down') OR published_at IS NOT NULL", name="ck_content_publications_published_at"
        ),
        CheckConstraint(
            "state NOT IN ('requested', 'closed') OR published_at IS NULL", name="ck_content_publications_never_published"
        ),
        CheckConstraint("hidden_at IS NULL OR state = 'published'", name="ck_content_publications_hidden"),
        CheckConstraint("(state IN ('requested', 'published')) = (ended_at IS NULL)", name="ck_content_publications_ended"),
        CheckConstraint("ended_at IS NULL OR state = 'closed' OR ended_by IS NOT NULL", name="ck_content_publications_ended_by"),
        CheckConstraint(
            "state <> 'taken_down' OR (end_reason IS NOT NULL AND length(trim(end_reason)) > 0)",
            name="ck_content_publications_takedown_reason",
        ),
        Index(
            "ux_content_publications_live",
            "asset_id",
            unique=True,
            postgresql_where=text("state IN ('requested', 'published')"),
            sqlite_where=text("state IN ('requested', 'published')"),
        ),
    )


class ContentUploadUsageModel(Base):
    """A student's upload quota in a tenant, charged by one conditional UPDATE."""

    __tablename__ = "content_upload_usage"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    usage_day: Mapped[date] = mapped_column(Date, nullable=False)
    uploads_on_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    stored_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        CheckConstraint("uploads_on_day >= 0", name="ck_content_upload_usage_uploads"),
        CheckConstraint("stored_bytes >= 0", name="ck_content_upload_usage_bytes"),
    )


class ContentRetryUsageModel(Base):
    """Retries per document per day, charged with the retry job."""

    __tablename__ = "content_retry_usage"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usage_day: Mapped[date] = mapped_column(Date, primary_key=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        _asset_reference("fk_content_retry_usage_asset"),
        CheckConstraint("retries >= 0", name="ck_content_retry_usage_retries"),
    )
