"""The ingestion worker's dispatch against the migrated PostgreSQL schema
(P3-6 §4, §14 "PostgreSQL").

Each job is claimed, dispatched and recorded in one transaction that locks
exactly that one row (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1), across one
bounded storage check and one bounded AI call. The AI-service is a fake
here; its contract (DUPLICATE for a repeated key) is proven against the real
service by the boundary gate.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import worker
from app.application.content.job_commands import HandleAICallbackCommand
from app.application.content.job_handlers import HandleAICallbackHandler
from app.bootstrap.container import sqlalchemy_content_uow
from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    VisibilityScope,
)
from app.domain.content.gateway import AIServiceDispatchResult
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.db.models.tenant_core import TenantModel
from tests.application.content.managed_storage import BUCKET, StoredObjects, managed

pytestmark = pytest.mark.asyncio(loop_scope="session")

EXTRACTED = {"characters": 900, "pages": 3, "method": "native_text"}


class FakeAIService:
    """Answers like the AI-service's dispatch contract: one task per
    idempotency key, so a repeated key gets the original task back."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (job id, idempotency key)
        self.tasks: dict[str, str] = {}
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.delay = 0.0

    def __call__(self):
        return self

    async def dispatch_ingestion_job(self, job, asset, source, actor) -> AIServiceDispatchResult:
        key = f"{job.id}-r{job.run_number}-a{job.attempt_count}"
        self.calls.append((job.id, key))
        self.entered.set()
        await self.release.wait()
        if self.delay:
            await asyncio.sleep(self.delay)
        status = "DUPLICATE" if key in self.tasks else "ACCEPTED"
        task = self.tasks.setdefault(key, f"task-{uuid4().hex}")
        return AIServiceDispatchResult(external_task_id=task, accepted_at=datetime.now(timezone.utc), status=status)


@pytest.fixture
def ai(monkeypatch):
    service = FakeAIService()
    objects = StoredObjects()
    monkeypatch.setattr(worker, "_dispatch_gateway", service)
    monkeypatch.setattr(worker, "_dispatch_storage", lambda: objects)
    monkeypatch.setattr(worker.settings, "object_storage_bucket", BUCKET)
    service.objects = objects
    return service


async def _queued_jobs(objects: StoredObjects, count: int) -> list[ContentIngestionJob]:
    tenant_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Worker",
                slug=f"wk-{uuid4().hex[:12]}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    jobs = []
    async with sqlalchemy_content_uow() as uow:
        source = ContentSource.create(
            code=f"SRC_{uuid4().hex[:6].upper()}",
            name="Worker",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.TENANT,
            created_by="usr-1",
            created_by_email="u@example.com",
            tenant_id=tenant_id,
        )
        await uow.sources.save_source(source)
        for i in range(count):
            asset = ContentAsset.create(
                source_id=source.id,
                file_name=f"w{i}.pdf",
                mime_type=AssetMimeType.PDF,
                file_size_bytes=10,
                content_sha256=uuid4().hex + uuid4().hex,
                storage_uri="s3://build/placeholder.pdf",
                created_by="usr-1",
                created_by_email="u@example.com",
                tenant_id=tenant_id,
            )
            managed(asset, objects)
            await uow.assets.save_asset(asset)
            job = ContentIngestionJob.create(asset_id=asset.id, source_id=source.id, tenant_id=tenant_id, created_by="usr-1")
            job.queue()
            await uow.jobs.save_job(job)
            jobs.append(job)
    return jobs


async def _states(ids: list[str]) -> dict[str, tuple[str, int, str | None]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT id, status, attempt_count, external_task_id FROM content_ingestion_jobs WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
        ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


async def test_two_workers_over_fifty_jobs_dispatch_each_exactly_once(ai, monkeypatch):
    jobs = await _queued_jobs(ai.objects, 50)
    ids = [j.id for j in jobs]
    monkeypatch.setattr(worker.settings, "worker_dispatch_batch", 1000)
    ai.delay = 0.005  # yield inside each locked step, so the two workers interleave

    await asyncio.gather(worker.run_dispatch_pass(), worker.run_dispatch_pass())

    ours = [job_id for job_id, _ in ai.calls if job_id in set(ids)]
    assert sorted(ours) == sorted(ids)  # every job dispatched, none twice
    states = await _states(ids)
    assert {s for s, _, _ in states.values()} == {"processing"}
    assert all(task is not None for _, _, task in states.values())


async def test_a_dispatch_in_progress_locks_exactly_its_own_row(ai):
    jobs = await _queued_jobs(ai.objects, 5)
    ids = [j.id for j in jobs]
    ai.release.clear()
    dispatching = asyncio.create_task(worker.run_dispatch_pass())
    await asyncio.wait_for(ai.entered.wait(), timeout=10)
    held = ai.calls[-1][0]
    try:
        async with SessionLocal() as session, session.begin():
            free = (
                (
                    await session.execute(
                        text("SELECT id FROM content_ingestion_jobs WHERE id = ANY(:ids) FOR UPDATE SKIP LOCKED"),
                        {"ids": ids},
                    )
                )
                .scalars()
                .all()
            )
        if held in ids:
            # Every other due job can be locked meanwhile; only the one being
            # dispatched is held.
            assert sorted(free) == sorted(i for i in ids if i != held)
            async with SessionLocal() as session, session.begin():
                with pytest.raises(DBAPIError):
                    await session.execute(
                        text("SELECT id FROM content_ingestion_jobs WHERE id = :id FOR UPDATE NOWAIT"), {"id": held}
                    )
    finally:
        ai.release.set()
        await dispatching


async def test_a_dispatch_cut_short_leaves_the_job_queued_and_reuses_its_key(ai):
    [job] = await _queued_jobs(ai.objects, 1)
    ai.release.clear()
    ai.entered.clear()
    crashed = asyncio.create_task(worker.run_dispatch_pass())
    while not any(job_id == job.id for job_id, _ in ai.calls):
        await asyncio.wait_for(ai.entered.wait(), timeout=10)
        ai.entered.clear()
    crashed.cancel()  # the worker dies mid-call: its transaction rolls back
    with pytest.raises(asyncio.CancelledError):
        await crashed

    assert (await _states([job.id]))[job.id] == ("queued", 1, None)
    ai.release.set()
    await worker.run_dispatch_pass()
    keys = [key for job_id, key in ai.calls if job_id == job.id]
    assert keys == [f"{job.id}-r1-a1"] * 2  # the same attempt and key both times
    status, attempt, task = (await _states([job.id]))[job.id]
    assert (status, attempt, task) == ("processing", 1, ai.tasks[keys[0]])


async def test_a_callback_during_a_dispatch_is_applied_after_its_commit(ai):
    [job] = await _queued_jobs(ai.objects, 1)
    ai.release.clear()
    ai.entered.clear()
    dispatching = asyncio.create_task(worker.run_dispatch_pass())
    while not any(job_id == job.id for job_id, _ in ai.calls):
        await asyncio.wait_for(ai.entered.wait(), timeout=10)
        ai.entered.clear()
    key = f"{job.id}-r1-a1"
    task = ai.tasks.setdefault(key, f"task-{uuid4().hex}")  # what the AI-service will answer

    async def callback() -> CallbackOutcome | None:
        async with sqlalchemy_content_uow() as uow:
            _, outcome = await HandleAICallbackHandler(uow).handle(
                HandleAICallbackCommand(
                    job_id=job.id,
                    tenant_id=job.tenant_id or "",
                    event_id=str(uuid4()),
                    event_type="stage_progress",
                    stage="extracted",
                    metrics=EXTRACTED,
                    external_task_id=task,
                    run_number=1,
                    attempt_count=1,
                )
            )
        return outcome

    applying = asyncio.create_task(callback())
    await asyncio.sleep(0.5)
    assert not applying.done()  # it waits on the job's row lock
    ai.release.set()
    await dispatching
    assert await asyncio.wait_for(applying, timeout=10) == CallbackOutcome.APPLIED
    assert (await _states([job.id]))[job.id] == ("extracted", 1, task)


async def test_a_dispatch_step_past_its_bound_is_rolled_back_without_holding_the_row(ai, monkeypatch):
    [job] = await _queued_jobs(ai.objects, 1)
    monkeypatch.setattr(worker, "dispatch_lock_bound_seconds", lambda: 1.0)
    ai.delay = 30  # the AI call never answers in time
    await worker.run_dispatch_pass()  # the timed-out job is excluded for this pass
    assert (await _states([job.id]))[job.id] == ("queued", 1, None)
    async with SessionLocal() as session, session.begin():  # nothing still holds it
        await session.execute(text("SELECT id FROM content_ingestion_jobs WHERE id = :id FOR UPDATE NOWAIT"), {"id": job.id})


async def test_no_claim_and_no_dispatch_without_the_database(ai, monkeypatch):
    jobs = await _queued_jobs(ai.objects, 1)
    down = create_async_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    monkeypatch.setattr(worker, "SessionLocal", async_sessionmaker(bind=down, expire_on_commit=False))
    calls_before = len(ai.calls)
    try:
        with pytest.raises(Exception):
            await worker.run_dispatch_pass()
    finally:
        await down.dispose()
    assert len(ai.calls) == calls_before
    assert (await _states([jobs[0].id]))[jobs[0].id][0] == "queued"
