"""content ingestion event ledger (M3-08)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-09 18:00:00.000000

Processed AI-service callbacks move from the JSON list
content_ingestion_jobs.processed_event_ids into content_ingestion_events:
one row per logical event (event_id), with the digest of its canonical
content and the outcome it had. The unique event_id makes deduplication a
database guarantee rather than a list kept on the job row.

Existing ids are copied with outcome 'legacy' and no digest: their content
was never recorded, so a later delivery with the same id is reported as a
legacy event, never as a verified identical duplicate. Ids longer than 64
characters or seen on more than one job cannot be keyed uniquely; they are
reported and skipped (only test data has produced such ids).

Downgrade restores the JSON column from the ledger (every recorded id per
job), then drops the table.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

JOBS = sa.table(
    "content_ingestion_jobs",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("processed_event_ids", sa.JSON),
)
EVENTS = sa.table(
    "content_ingestion_events",
    sa.column("event_id", sa.String),
    sa.column("job_id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("outcome", sa.String),
    sa.column("received_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.create_table(
        "content_ingestion_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=True),
        sa.Column("external_task_id", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=True),
        sa.Column("stage", sa.String(length=20), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["content_ingestion_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_content_ingestion_events_job_id", "content_ingestion_events", ["job_id"]
    )

    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    copied = skipped = 0
    for job_id, tenant_id, ids in bind.execute(
        sa.select(JOBS.c.id, JOBS.c.tenant_id, JOBS.c.processed_event_ids)
    ):
        for event_id in ids or []:
            if not isinstance(event_id, str) or len(event_id) > 64 or event_id in seen:
                skipped += 1
                continue
            seen.add(event_id)
            bind.execute(
                EVENTS.insert().values(
                    event_id=event_id,
                    job_id=job_id,
                    tenant_id=tenant_id,
                    outcome="legacy",
                    received_at=now,
                )
            )
            copied += 1
    if copied or skipped:
        print(f"0023: copied {copied} legacy event ids, skipped {skipped}")

    op.drop_column("content_ingestion_jobs", "processed_event_ids")


def downgrade() -> None:
    op.add_column(
        "content_ingestion_jobs",
        sa.Column(
            "processed_event_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    bind = op.get_bind()
    by_job: dict[str, list[str]] = {}
    for event_id, job_id in bind.execute(sa.select(EVENTS.c.event_id, EVENTS.c.job_id)):
        by_job.setdefault(job_id, []).append(event_id)
    for job_id, ids in by_job.items():
        bind.execute(
            JOBS.update().where(JOBS.c.id == job_id).values(processed_event_ids=sorted(ids))
        )
    op.alter_column("content_ingestion_jobs", "processed_event_ids", server_default=None)

    op.drop_index("ix_content_ingestion_events_job_id", table_name="content_ingestion_events")
    op.drop_table("content_ingestion_events")
