"""tenant_invitations

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-03 22:00:00.000000

Invitations to join a tenant (M2 design 3.6). A separate table because the
invitee may not have an account yet. Only a hash of the invitation token is
stored. A partial unique index allows at most one pending invitation per
email per tenant; accepted and revoked invitations are kept as history.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

PENDING = sa.text("status = 'pending'")


def upgrade() -> None:
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_tenant_invitations_token_hash"),
    )
    op.create_index(
        "uq_tenant_invitations_pending_email",
        "tenant_invitations",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=PENDING,
        sqlite_where=PENDING,
    )
    op.create_index("ix_tenant_invitations_tenant_id", "tenant_invitations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_invitations_tenant_id", table_name="tenant_invitations")
    op.drop_index("uq_tenant_invitations_pending_email", table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
