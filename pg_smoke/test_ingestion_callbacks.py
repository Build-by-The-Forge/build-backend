"""Ingestion callbacks against the migrated PostgreSQL schema (M3-08).

Competing callbacks for one job are serialised by SELECT ... FOR UPDATE, and
the event ledger is persisted in the same transaction as the transition.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.application.content.job_commands import HandleAICallbackCommand
from app.application.content.job_handlers import HandleAICallbackHandler
from app.bootstrap.container import sqlalchemy_content_uow
from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    VisibilityScope,
)
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.db.models.tenant_core import TenantModel

pytestmark = pytest.mark.asyncio(loop_scope="session")

EXTRACTED = {"characters": 900, "pages": 3, "method": "native_text"}


async def _processing_job() -> ContentIngestionJob:
    tenant_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Callbacks",
                slug=f"cb-{uuid4().hex[:12]}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    async with sqlalchemy_content_uow() as uow:
        source = ContentSource.create(
            code=f"SRC_{uuid4().hex[:6].upper()}",
            name="Callbacks",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.TENANT,
            created_by="usr-1",
            created_by_email="u@example.com",
            tenant_id=tenant_id,
        )
        await uow.sources.save_source(source)
        asset = ContentAsset.create(
            source_id=source.id,
            file_name="cb.pdf",
            mime_type=AssetMimeType.PDF,
            file_size_bytes=10,
            content_sha256="c" * 64,
            storage_uri="s3://build/cb.pdf",
            created_by="usr-1",
            created_by_email="u@example.com",
            tenant_id=tenant_id,
        )
        await uow.assets.save_asset(asset)
        job = ContentIngestionJob.create(asset_id=asset.id, source_id=source.id, tenant_id=tenant_id, created_by="usr-1")
        job.queue()
        job.record_dispatch(f"task-{uuid4().hex}")
        await uow.jobs.save_job(job)
    return job


def _cmd(job: ContentIngestionJob, event_id: str, **kwargs) -> HandleAICallbackCommand:
    return HandleAICallbackCommand(
        job_id=job.id,
        tenant_id=job.tenant_id or "",
        event_id=event_id,
        external_task_id=job.external_task_id or "",
        run_number=job.run_number,
        attempt_count=job.attempt_count,
        **kwargs,
    )


async def _apply(cmd: HandleAICallbackCommand, hold: float = 0.0) -> CallbackOutcome | None:
    async with sqlalchemy_content_uow() as uow:
        _, outcome = await HandleAICallbackHandler(uow).handle(cmd)
        await asyncio.sleep(hold)  # keep the row lock while the other call waits
    return outcome


async def _status_and_ledger(job_id: str) -> tuple[str, list[tuple[str, str]]]:
    async with SessionLocal() as session:
        status = (
            await session.execute(text("SELECT status FROM content_ingestion_jobs WHERE id = :id"), {"id": job_id})
        ).scalar_one()
        rows = (
            await session.execute(
                text("SELECT event_id, outcome FROM content_ingestion_events WHERE job_id = :id ORDER BY event_id"),
                {"id": job_id},
            )
        ).all()
    return status, [(r[0], r[1]) for r in rows]


async def test_two_stage_events_racing_apply_exactly_once():
    job = await _processing_job()
    # Event ids are global in the ledger: unique per run, so the test repeats
    # against the same database.
    first = _cmd(job, f"evt-a-{uuid4().hex}", event_type="stage_progress", stage="extracted", metrics=EXTRACTED)
    second = _cmd(job, f"evt-b-{uuid4().hex}", event_type="stage_progress", stage="extracted", metrics=EXTRACTED)

    outcomes = await asyncio.gather(_apply(first, hold=0.3), _apply(second, hold=0.3))

    assert sorted(o.value for o in outcomes if o) == ["applied", "superseded"]
    status, ledger = await _status_and_ledger(job.id)
    assert status == IngestionStatus.EXTRACTED.value
    assert sorted(outcome for _, outcome in ledger) == ["applied", "superseded"]


async def test_the_same_event_delivered_concurrently_is_applied_once():
    job = await _processing_job()
    event_id = f"evt-same-{uuid4().hex}"
    cmd = _cmd(job, event_id, event_type="job_failed", error_code="X", error_message="x")

    outcomes = await asyncio.gather(_apply(cmd, hold=0.3), _apply(cmd, hold=0.3))

    assert sorted(o.value for o in outcomes if o) == ["applied", "duplicate"]
    status, ledger = await _status_and_ledger(job.id)
    assert status == IngestionStatus.FAILED.value
    assert ledger == [(event_id, "applied")]


async def test_a_not_allowed_event_leaves_no_ledger_row():
    job = await _processing_job()
    outcome = await _apply(_cmd(job, "evt-early", event_type="job_completed"))
    assert outcome is CallbackOutcome.NOT_ALLOWED
    assert await _status_and_ledger(job.id) == (IngestionStatus.PROCESSING.value, [])


async def test_deleting_a_job_removes_its_ledger():
    job = await _processing_job()
    event_id = f"evt-del-{uuid4().hex}"
    await _apply(_cmd(job, event_id, event_type="job_failed"))
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM content_ingestion_jobs WHERE id = :id"), {"id": job.id})
        await session.commit()
        left = (
            await session.execute(
                text("SELECT count(*) FROM content_ingestion_events WHERE event_id = :event_id"), {"event_id": event_id}
            )
        ).scalar_one()
    assert left == 0
