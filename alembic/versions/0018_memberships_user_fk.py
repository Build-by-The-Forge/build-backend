"""memberships.user_id references users.id

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-03 19:00:00.000000

memberships.user_id was a bare string, so a membership could name a user
that does not exist. This adds the foreign key. Rows that already point at
a missing user would make the constraint fail half-way, so the upgrade
checks first and stops with a report instead; those rows need a decision
(re-link or delete) by an operator, never a silent cleanup here.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

CONSTRAINT = "fk_memberships_user_id_users"
REPORT_LIMIT = 10


def upgrade() -> None:
    orphans = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT m.id FROM memberships m "
                "LEFT JOIN users u ON u.id = m.user_id "
                "WHERE u.id IS NULL ORDER BY m.id"
            )
        )
        .scalars()
        .all()
    )
    if orphans:
        shown = ", ".join(orphans[:REPORT_LIMIT])
        more = f" (and {len(orphans) - REPORT_LIMIT} more)" if len(orphans) > REPORT_LIMIT else ""
        raise RuntimeError(
            f"{len(orphans)} membership(s) reference users that do not exist; "
            f"re-link or delete them before upgrading. Membership ids: {shown}{more}"
        )

    # batch mode recreates the table on SQLite, which cannot add constraints.
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.create_foreign_key(
            CONSTRAINT, "users", ["user_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="foreignkey")
