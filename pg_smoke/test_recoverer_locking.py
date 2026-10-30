"""Recoverer and callbacks serialize on the same PostgreSQL job-row lock."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.content.job_commands import HandleAICallbackCommand
from app.application.content.job_handlers import HandleAICallbackHandler
from app.bootstrap.container import sqlalchemy_content_uow
from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetMimeType, AuthorityLevel, ContentSourceType, IngestionStatus, VisibilityScope
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from app.infrastructure.db.models.content import ContentIngestionJobModel
from app.infrastructure.db.models.tenant_core import TenantModel

pytestmark = pytest.mark.asyncio(loop_scope="session")
EXTRACTED = {"characters": 900, "pages": 3, "method": "native_text"}


async def _overdue_job() -> ContentIngestionJob:
    tenant_id, suffix = str(uuid4()), uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Recoverer",
                slug=f"recoverer-{suffix}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    async with sqlalchemy_content_uow() as uow:
        source = ContentSource.create(
            code=f"REC_{suffix.upper()}",
            name="Recoverer",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.TENANT,
            created_by="usr-recoverer",
            created_by_email="recoverer@example.com",
            tenant_id=tenant_id,
        )
        await uow.sources.save_source(source)
        asset = ContentAsset.create(
            source_id=source.id,
            file_name="recoverer.pdf",
            mime_type=AssetMimeType.PDF,
            file_size_bytes=10,
            content_sha256=uuid4().hex * 2,
            storage_uri="s3://build/recoverer.pdf",
            created_by="usr-recoverer",
            created_by_email="recoverer@example.com",
            tenant_id=tenant_id,
            ingestion_status=IngestionStatus.PROCESSING,
        )
        await uow.assets.save_asset(asset)
        job = ContentIngestionJob.create(
            asset_id=asset.id,
            source_id=source.id,
            tenant_id=tenant_id,
            created_by="usr-recoverer",
        )
        job.queue()
        job.record_dispatch(f"task-{uuid4().hex}")
        job.updated_at = now - timedelta(hours=2)
        await uow.jobs.save_job(job)
    return job


async def _other_active_job_ids(job_id: str) -> set[str]:
    async with SessionLocal() as session:
        ids = (
            await session.execute(
                select(ContentIngestionJobModel.id).where(
                    ContentIngestionJobModel.status.in_(
                        (
                            IngestionStatus.PROCESSING.value,
                            IngestionStatus.EXTRACTED.value,
                            IngestionStatus.CHUNKED.value,
                            IngestionStatus.INDEXED.value,
                        )
                    )
                )
            )
        ).scalars()
        return {value for value in ids if value != job_id}


def _callback(job: ContentIngestionJob, event_id: str) -> HandleAICallbackCommand:
    return HandleAICallbackCommand(
        job_id=job.id,
        tenant_id=job.tenant_id or "",
        event_id=event_id,
        external_task_id=job.external_task_id or "",
        run_number=job.run_number,
        attempt_count=job.attempt_count,
        event_type="stage_progress",
        stage="extracted",
        metrics=EXTRACTED,
    )


async def _apply_callback(
    command: HandleAICallbackCommand,
    started: asyncio.Event | None = None,
    hold_lock: bool = False,
):
    async with sqlalchemy_content_uow() as uow:
        if started is not None:
            if hold_lock:
                await uow.jobs.get_job_for_update(command.job_id)
            started.set()
            if hold_lock:
                await asyncio.sleep(0.3)
        result = await HandleAICallbackHandler(uow).handle(command)
        return result[1]


async def test_recoverer_and_callback_row_locks_serialize_in_both_orders():
    recovery_first = await _overdue_job()
    excluded = await _other_active_job_ids(recovery_first.id)
    callback_started = asyncio.Event()

    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            claimed = await uow.jobs.claim_next_overdue_job(excluded, 1, 1, 3600)
            assert claimed is not None and claimed.id == recovery_first.id
            callback = asyncio.create_task(_apply_callback(_callback(recovery_first, f"cb-{uuid4().hex}"), callback_started))
            await asyncio.wait_for(callback_started.wait(), timeout=5)
            await asyncio.sleep(0.2)
            assert not callback.done()

    assert (await callback).value == "applied"

    callback_first = await _overdue_job()
    excluded = await _other_active_job_ids(callback_first.id)
    started = asyncio.Event()
    callback = asyncio.create_task(_apply_callback(_callback(callback_first, f"cb-{uuid4().hex}"), started, hold_lock=True))
    await asyncio.wait_for(started.wait(), timeout=5)

    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            claimed = await uow.jobs.claim_next_overdue_job(excluded, 1, 1, 3600)
            assert claimed is None

    assert (await callback).value == "applied"
