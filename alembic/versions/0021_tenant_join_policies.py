"""tenant_join_policies

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-03 23:00:00.000000

Decision D5: a tenant may let students with a verified address on its
institutional domains join without an invitation. One row per tenant; no
row (or enabled = false) means email-domain join is off, which is the
default for every tenant.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_join_policies",
        sa.Column("tenant_id", sa.String(length=36), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("default_role", sa.String(length=30), nullable=False, server_default="student"),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    # Dropping the table would silently delete tenants' join settings.
    rows = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM tenant_join_policies")).scalar_one()
    if rows:
        raise RuntimeError(
            f"cannot downgrade from 0021: tenant_join_policies holds {rows} row(s); remove or export them explicitly first"
        )
    op.drop_table("tenant_join_policies")
