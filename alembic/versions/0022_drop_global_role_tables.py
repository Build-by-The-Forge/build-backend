"""drop the unused global role tables (decision D7)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-04 12:00:00.000000

roles, permissions, role_assignments and role_permissions (migrations
0001/0002) were a second, never-used role system: authorization reads only
memberships.role through the in-code permission map, nothing ever wrote a
row to these tables, and AI-service does not use them. M2 decision D7
removes them.

They are dropped only if all four are empty. If any holds rows, the upgrade
refuses, reports the counts and changes nothing: those rows would be
historical role data needing an explicit decision (export or discard) by
an operator, never a silent DROP.

Downgrade recreates the four tables exactly as 0001 + 0002 left them, but
empty: dropped rows cannot be restored, which is why the upgrade refuses
when there are any.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

# Dependency order: association/assignment tables first.
TABLES = ("role_permissions", "role_assignments", "permissions", "roles")


def upgrade() -> None:
    bind = op.get_bind()
    counts = {table: bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one() for table in TABLES}
    populated = {table: n for table, n in counts.items() if n}
    if populated:
        found = ", ".join(f"{table}={n}" for table, n in populated.items())
        raise RuntimeError(
            f"cannot drop the global role tables: they hold rows ({found}). "
            "This is historical role data: export or discard it explicitly "
            "before upgrading to 0022."
        )

    for table in TABLES:
        op.drop_table(table)


def downgrade() -> None:
    """Recreate the 0001 + 0002 shape, empty."""
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="roles_name_key"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),
    )
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_role_assignments_user_role"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("permission_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
