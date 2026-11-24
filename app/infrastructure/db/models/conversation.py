"""M3-F: conversations and their cited answers (docs/m3-f-design.md).

The backend issues every ID and owns the rows. The AI service keeps nothing
of a conversation. Mirrors migration 0033 exactly: scripts/check_schema_drift.py
fails if the two disagree. Every child row carries its tenant, and every
reference to its parent is composite, so the database keeps a conversation's
rows in one tenant (see the migration for the one exception, ``source_id``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=text("now()"))


class ConversationModel(Base):
    """One student's conversation in one tenant. Removing the user or the
    tenant removes it, and everything below it."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
        Index("ix_conversations_owner_updated", "tenant_id", "user_id", text("updated_at DESC"), text("id DESC")),
        CheckConstraint("status IN ('active')", name="ck_conversations_status"),
        CheckConstraint("title IS NULL OR length(trim(title)) > 0", name="ck_conversations_title"),
        CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="ck_conversations_expiry"),
    )


class ConversationMessageModel(Base):
    """A question or an answer. ``seq`` orders them, so a question and its
    answer never swap. A redacted answer holds the fixed notice."""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = _stamp()

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_messages_conversation",
            ondelete="CASCADE",
        ),
        UniqueConstraint("conversation_id", "seq", name="uq_conversation_messages_seq"),
        UniqueConstraint("tenant_id", "id", name="uq_conversation_messages_tenant_id"),
        UniqueConstraint("tenant_id", "conversation_id", "id", name="uq_conversation_messages_tenant_conversation_id"),
        CheckConstraint("seq > 0", name="ck_conversation_messages_seq"),
        CheckConstraint("role IN ('student', 'assistant')", name="ck_conversation_messages_role"),
        CheckConstraint("length(content) > 0", name="ck_conversation_messages_content"),
        CheckConstraint(
            "(role = 'student' AND grounded IS NULL AND NOT redacted) OR (role = 'assistant' AND grounded IS NOT NULL)",
            name="ck_conversation_messages_shape",
        ),
    )


class ConversationCitationModel(Base):
    """A source an answer cites. The excerpt is cut from the cited passage,
    never generated, and holds at most 500 characters."""

    __tablename__ = "conversation_citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    message_id: Mapped[str] = mapped_column(String(36), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_sources.id", ondelete="RESTRICT"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            name="fk_conversation_citations_message",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_conversation_citations_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", "number", name="uq_conversation_citations_number"),
        Index("ix_conversation_citations_asset", "asset_id"),
        CheckConstraint("number >= 1", name="ck_conversation_citations_number"),
        CheckConstraint("length(excerpt) BETWEEN 1 AND 500", name="ck_conversation_citations_excerpt"),
        CheckConstraint(
            "(page_start IS NULL OR page_start >= 0) AND (page_end IS NULL OR page_end >= 0)"
            " AND (page_start IS NULL OR page_end IS NULL OR page_end >= page_start)",
            name="ck_conversation_citations_pages",
        ),
    )


class ConversationMessageSourceModel(Base):
    """Every ``(asset, run, attempt)`` the AI service reported for an answer,
    cited or not. IDs only: redaction works from these rows."""

    __tablename__ = "conversation_message_sources"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    message_id: Mapped[str] = mapped_column(String(36), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("message_id", "asset_id", "run_number", "attempt", name="pk_conversation_message_sources"),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            name="fk_conversation_message_sources_message",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_conversation_message_sources_asset",
            ondelete="RESTRICT",
        ),
        Index("ix_conversation_message_sources_asset", "asset_id"),
        CheckConstraint("run_number >= 1 AND attempt >= 1", name="ck_conversation_message_sources_version"),
    )


class ConversationTurnKeyModel(Base):
    """A send's idempotency key, its lease and its fencing generation."""

    __tablename__ = "conversation_turn_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    student_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assistant_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_turn_keys_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "student_message_id"],
            [
                "conversation_messages.tenant_id",
                "conversation_messages.conversation_id",
                "conversation_messages.id",
            ],
            name="fk_conversation_turn_keys_student_message",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "assistant_message_id"],
            [
                "conversation_messages.tenant_id",
                "conversation_messages.conversation_id",
                "conversation_messages.id",
            ],
            name="fk_conversation_turn_keys_assistant_message",
            ondelete="CASCADE",
        ),
        UniqueConstraint("conversation_id", "idempotency_key", name="uq_conversation_turn_keys_key"),
        CheckConstraint("length(idempotency_key) > 0", name="ck_conversation_turn_keys_key"),
        CheckConstraint(
            "length(question_sha256) = 64 AND question_sha256 = lower(question_sha256)",
            name="ck_conversation_turn_keys_sha",
        ),
        CheckConstraint("state IN ('pending', 'stored')", name="ck_conversation_turn_keys_state"),
        CheckConstraint("generation >= 1", name="ck_conversation_turn_keys_generation"),
        CheckConstraint(
            "(state = 'stored' AND student_message_id IS NOT NULL AND assistant_message_id IS NOT NULL)"
            " OR (state = 'pending' AND student_message_id IS NULL AND assistant_message_id IS NULL)",
            name="ck_conversation_turn_keys_turn",
        ),
    )
