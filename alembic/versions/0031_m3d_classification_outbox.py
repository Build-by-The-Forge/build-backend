"""M3-D PR 5: tenant authority, operator runs and the scope-assignment outbox.

Revision ID: 0031
Revises: 0030

- ``content_authority_authorizations``: a tenant authority's written
  authorization for the operator command (design: operator classification,
  condition 1). Who gave it, when, what it covers, and a reference to the
  document; revocable and optionally expiring. Checked on every run.
- ``content_classification_runs``: one row per applied operator run, naming
  the authorization relied on. 0030's classifications already require a
  ``run_id`` from the operator; it now references a run of the same tenant.
- ``content_scope_assignments``: the outbox. A row is (tenant, asset, scope,
  version), written in the same transaction as the decision behind it, with
  who decided. The version only rises per document. A row is pending until
  the AI service returns that version, or a higher one (superseded).
  Lowerings (any scope but institutional) are sent first, and the pending
  ones are the ``denied_assets`` every retrieving call carries.

Nothing existing changes: no rows are written, and an existing classification
whose run_id names no run makes the upgrade fail rather than be repaired.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_authority_authorizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authority_name", sa.Text(), nullable=False),
        sa.Column("authority_role", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("covers", sa.Text(), nullable=False),
        sa.Column("document_reference", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_content_authority_tenant_id"),
        sa.CheckConstraint("length(trim(authority_name)) > 0", name="ck_content_authority_name"),
        sa.CheckConstraint("length(trim(authority_role)) > 0", name="ck_content_authority_role"),
        sa.CheckConstraint("length(trim(covers)) > 0", name="ck_content_authority_covers"),
        sa.CheckConstraint("length(trim(document_reference)) > 0", name="ck_content_authority_document"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > granted_at", name="ck_content_authority_expiry"),
        sa.CheckConstraint("(revoked_at IS NULL) = (revoked_by IS NULL)", name="ck_content_authority_revoked"),
    )

    op.create_table(
        "content_classification_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authorization_id", sa.String(36), nullable=False),
        sa.Column("operator_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("requested", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "authorization_id"],
            ["content_authority_authorizations.tenant_id", "content_authority_authorizations.id"],
            name="fk_content_runs_authorization",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_content_runs_tenant_id"),
        sa.CheckConstraint("requested > 0", name="ck_content_runs_requested"),
    )
    # An operator's classification names a run of its own tenant. Existing
    # rows that name no run fail here: nothing is repaired.
    op.create_foreign_key(
        "fk_content_classifications_run",
        "content_ownership_classifications",
        "content_classification_runs",
        ["tenant_id", "run_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "content_scope_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lowers", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("state", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        # The asset can't be deleted while an assignment names it (a pending
        # lowering must never be lost); a tenant's cascade removes both.
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_scope_assignments_asset",
        ),
        sa.UniqueConstraint("tenant_id", "asset_id", "version", name="uq_content_scope_assignments_version"),
        sa.CheckConstraint("scope IN ('institutional', 'personal', 'unknown')", name="ck_content_scope_assignments_scope"),
        sa.CheckConstraint("version > 0", name="ck_content_scope_assignments_version"),
        sa.CheckConstraint("lowers = (scope <> 'institutional')", name="ck_content_scope_assignments_lowers"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_content_scope_assignments_reason"),
        sa.CheckConstraint("state IN ('pending', 'acknowledged', 'superseded')", name="ck_content_scope_assignments_state"),
        sa.CheckConstraint("(state = 'pending') = (settled_at IS NULL)", name="ck_content_scope_assignments_settled"),
        sa.CheckConstraint("attempts >= 0", name="ck_content_scope_assignments_attempts"),
    )
    # The dispatcher's queue: lowerings first, then the oldest due.
    op.create_index(
        "ix_content_scope_assignments_due",
        "content_scope_assignments",
        [sa.text("lowers DESC"), "next_attempt_at"],
        postgresql_where=sa.text("state = 'pending'"),
    )
    # A tenant's pending lowerings are its denied_assets.
    op.create_index(
        "ix_content_scope_assignments_denied",
        "content_scope_assignments",
        ["tenant_id", "asset_id"],
        postgresql_where=sa.text("state = 'pending' AND lowers"),
    )


def downgrade() -> None:
    op.drop_index("ix_content_scope_assignments_denied", table_name="content_scope_assignments")
    op.drop_index("ix_content_scope_assignments_due", table_name="content_scope_assignments")
    op.drop_table("content_scope_assignments")
    op.drop_constraint("fk_content_classifications_run", "content_ownership_classifications", type_="foreignkey")
    op.drop_table("content_classification_runs")
    op.drop_table("content_authority_authorizations")
