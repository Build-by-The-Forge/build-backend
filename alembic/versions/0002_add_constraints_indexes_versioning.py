"""Add database constraints, indexes, and versioning columns for optimistic concurrency control.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-26

Changes:
- Add unique constraint on (resource, action) for permissions table
- Add unique constraint on (user_id, role_id) for role_assignments table
- Add indexes for query optimization:
  - sessions.refresh_token_hash (for token lookups)
  - sessions.user_id (for user session queries)
  - devices.device_fingerprint (for device identification)
  - login_events.created_at (for time-range queries)
- Add version columns to mutable aggregates for optimistic concurrency control:
  - users.version (default: 0)
  - sessions.version (default: 0)
  - devices.version (default: 0)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # For SQLite, use batch mode for schema modifications
    with op.batch_alter_table("permissions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_permissions_resource_action", ["resource", "action"]
        )

    with op.batch_alter_table("role_assignments", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_role_assignments_user_role", ["user_id", "role_id"]
        )

    # Add indexes for query optimization
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index("idx_sessions_refresh_token_hash", ["refresh_token_hash"])
        batch_op.create_index("idx_sessions_user_id", ["user_id"])

    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.create_index("idx_devices_device_fingerprint", ["device_fingerprint"])

    with op.batch_alter_table("login_events", schema=None) as batch_op:
        batch_op.create_index("idx_login_events_created_at", ["created_at"])
        batch_op.create_index("idx_login_events_user_id", ["user_id"])

    # Add version columns for optimistic concurrency control
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    # Remove version columns
    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.drop_column("version")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_column("version")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("version")

    # Remove indexes
    with op.batch_alter_table("login_events", schema=None) as batch_op:
        batch_op.drop_index("idx_login_events_user_id")
        batch_op.drop_index("idx_login_events_created_at")

    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.drop_index("idx_devices_device_fingerprint")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index("idx_sessions_user_id")
        batch_op.drop_index("idx_sessions_refresh_token_hash")

    # Remove unique constraints
    with op.batch_alter_table("role_assignments", schema=None) as batch_op:
        batch_op.drop_constraint("uq_role_assignments_user_role", type_="unique")

    with op.batch_alter_table("permissions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_permissions_resource_action", type_="unique")
