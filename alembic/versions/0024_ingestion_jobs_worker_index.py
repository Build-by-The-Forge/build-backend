"""ingestion worker's selection index (P3-6 §11)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-28 20:00:00.000000

One partial index serves the worker's loops, each of which takes one due
job at a time (FOR UPDATE SKIP LOCKED, ORDER BY created_at): the dispatcher
(queued and due), the retrier (failed) and the recoverer (in flight). Ready
jobs, the bulk of the table, are left out, so the index stays small. No
table or column changes.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

INDEX = "ix_content_ingestion_jobs_worker_due"
WORKER_STATUSES = "status IN ('queued', 'failed', 'processing', 'extracted', 'chunked', 'indexed')"


def upgrade() -> None:
    op.create_index(
        INDEX,
        "content_ingestion_jobs",
        ["status", "next_retry_at", "created_at"],
        postgresql_where=sa.text(WORKER_STATUSES),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="content_ingestion_jobs")
