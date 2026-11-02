"""accepted registrations, waiting for the worker

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-02 09:00:00.000000

A registration is recorded here before it's answered, whichever the email. The worker
looks for the account and removes the row, so a row holds a password hash only briefly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pending_registrations_created_at", "pending_registrations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_pending_registrations_created_at", table_name="pending_registrations")
    op.drop_table("pending_registrations")
