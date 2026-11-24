"""M3-F: conversations, their messages, citations, sources and turn keys.

Revision ID: 0033
Revises: 0032

Design: docs/m3-f-design.md (approved in #81, amended for provenance in #83).
The backend issues every ID and owns the rows; the AI service keeps nothing.

- ``conversations``: one student's conversation in one tenant. Removing the
  user or the tenant removes it, and so everything below.
- ``conversation_messages``: the turns, ordered by ``seq`` (unique per
  conversation, so a question and its answer never swap). A student's
  message has no ``grounded`` and is never redacted. ``redacted`` marks an
  answer whose text was replaced by the fixed notice.
- ``conversation_citations``: the sources an answer cites, with the excerpt
  (at most 500 characters, cut from the cited passage, never generated).
- ``conversation_message_sources``: every ``(asset, run, attempt)`` the AI
  service reported in ``sources_used``, cited or not. IDs only, no text.
  Redaction works from this table, not from citations.
- ``conversation_turn_keys``: the idempotency key of a send, its lease and
  its fencing ``generation``. A ``stored`` key names the two messages of the
  turn it stored, both in its own conversation.

Tenant integrity: every child table carries ``tenant_id`` and every reference
to a parent is composite, ``(tenant_id, parent)``, so the database itself
keeps a message, a citation, a source row and a key in their conversation's
tenant, and a cited or used document in that tenant too. The one exception
is ``conversation_citations.source_id``: ``content_sources`` has no
``(tenant_id, id)`` key, and M3-D owns that table, so it is a plain
reference and the application takes it from the document's own record.

``asset_id`` references are RESTRICT: a document is never hard-deleted, and
deleting one is a redaction, not a cascade.

Nothing existing changes and no rows are written. **Downgrade drops all five
tables and every conversation in them.** That loses no data while the
conversation routes are off (they ship disabled until the retention decision
exists); once students have conversations, a downgrade is a deletion of
their history and needs the same approval as deleting it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _now() -> sa.sql.elements.ColumnElement:
    return sa.func.now()


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(80), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
        sa.CheckConstraint("status IN ('active')", name="ck_conversations_status"),
        sa.CheckConstraint("title IS NULL OR length(trim(title)) > 0", name="ck_conversations_title"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="ck_conversations_expiry"),
    )
    # The list is a student's conversations in a tenant, newest first.
    op.create_index(
        "ix_conversations_owner_updated",
        "conversations",
        ["tenant_id", "user_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_messages_conversation",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_conversation_messages_seq"),
        # The targets of the child tables' composite keys.
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversation_messages_tenant_id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", "id", name="uq_conversation_messages_tenant_conversation_id"),
        sa.CheckConstraint("seq > 0", name="ck_conversation_messages_seq"),
        sa.CheckConstraint("role IN ('student', 'assistant')", name="ck_conversation_messages_role"),
        sa.CheckConstraint("length(content) > 0", name="ck_conversation_messages_content"),
        # A student's message has no grounding and is never redacted; an
        # answer always says whether it was grounded.
        sa.CheckConstraint(
            "(role = 'student' AND grounded IS NULL AND NOT redacted) OR (role = 'assistant' AND grounded IS NOT NULL)",
            name="ck_conversation_messages_shape",
        ),
    )

    op.create_table(
        "conversation_citations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("content_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            name="fk_conversation_citations_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_conversation_citations_asset",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("message_id", "number", name="uq_conversation_citations_number"),
        sa.CheckConstraint("number >= 1", name="ck_conversation_citations_number"),
        sa.CheckConstraint("length(excerpt) BETWEEN 1 AND 500", name="ck_conversation_citations_excerpt"),
        sa.CheckConstraint(
            "(page_start IS NULL OR page_start >= 0) AND (page_end IS NULL OR page_end >= 0)"
            " AND (page_start IS NULL OR page_end IS NULL OR page_end >= page_start)",
            name="ck_conversation_citations_pages",
        ),
    )
    op.create_index("ix_conversation_citations_asset", "conversation_citations", ["asset_id"])

    op.create_table(
        "conversation_message_sources",
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("message_id", "asset_id", "run_number", "attempt", name="pk_conversation_message_sources"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            name="fk_conversation_message_sources_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_conversation_message_sources_asset",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("run_number >= 1 AND attempt >= 1", name="ck_conversation_message_sources_version"),
    )
    # Deleting or losing a document finds every message that used it.
    op.create_index("ix_conversation_message_sources_asset", "conversation_message_sources", ["asset_id"])

    op.create_table(
        "conversation_turn_keys",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("question_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("student_message_id", sa.String(36), nullable=True),
        sa.Column("assistant_message_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_turn_keys_conversation",
            ondelete="CASCADE",
        ),
        # A stored turn's messages are in this key's own conversation. A NULL
        # message (a pending key) checks nothing, which is the intent: the
        # shape constraint below says when they must be present.
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "student_message_id"],
            [
                "conversation_messages.tenant_id",
                "conversation_messages.conversation_id",
                "conversation_messages.id",
            ],
            name="fk_conversation_turn_keys_student_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "assistant_message_id"],
            [
                "conversation_messages.tenant_id",
                "conversation_messages.conversation_id",
                "conversation_messages.id",
            ],
            name="fk_conversation_turn_keys_assistant_message",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("conversation_id", "idempotency_key", name="uq_conversation_turn_keys_key"),
        sa.CheckConstraint("length(idempotency_key) > 0", name="ck_conversation_turn_keys_key"),
        sa.CheckConstraint(
            "length(question_sha256) = 64 AND question_sha256 = lower(question_sha256)",
            name="ck_conversation_turn_keys_sha",
        ),
        sa.CheckConstraint("state IN ('pending', 'stored')", name="ck_conversation_turn_keys_state"),
        sa.CheckConstraint("generation >= 1", name="ck_conversation_turn_keys_generation"),
        # A stored key names both messages of its turn; a pending one names none.
        sa.CheckConstraint(
            "(state = 'stored' AND student_message_id IS NOT NULL AND assistant_message_id IS NOT NULL)"
            " OR (state = 'pending' AND student_message_id IS NULL AND assistant_message_id IS NULL)",
            name="ck_conversation_turn_keys_turn",
        ),
    )


def downgrade() -> None:
    # Drops every conversation (see the module docstring).
    op.drop_table("conversation_turn_keys")
    op.drop_index("ix_conversation_message_sources_asset", table_name="conversation_message_sources")
    op.drop_table("conversation_message_sources")
    op.drop_index("ix_conversation_citations_asset", table_name="conversation_citations")
    op.drop_table("conversation_citations")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
