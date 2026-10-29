from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from app.application.content.job_handlers import DispatchAttemptOutcome, DispatchIngestionJobHandler
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.db.timeouts import set_transaction_timeouts
from app.domain.content.enums import IngestionStatus
from app.domain.content.gateway import JobTenantMissing, SystemDispatchActor
from app.events.event_bus import EventBus
from app.infrastructure.content.ai_gateway import HttpAIServiceIngestionGateway
from app.infrastructure.content.orphan_sweeper import sweep_orphaned_objects
from app.infrastructure.content.s3_object_storage import S3ObjectStorage
from app.infrastructure.content.unit_of_work import ContentUnitOfWork

logger = structlog.get_logger(__name__)
HEALTH_PATH = Path(os.getenv("WORKER_HEALTH_PATH", "/tmp/build-backend-worker-health.json"))


def retry_delay_seconds(attempt: int, base: int, cap: int, random_value: float | None = None) -> int:
    if attempt < 1 or base < 1 or cap < base:
        raise ValueError("attempt and base must be positive, and cap must be at least base")
    bounded = base
    for _ in range(attempt - 1):
        if bounded >= cap:
            break
        bounded = min(bounded * 2, cap)
    sample = random.random() if random_value is None else random_value
    if not 0 <= sample <= 1:
        raise ValueError("random_value must be between zero and one")
    return max(1, round(bounded * (0.8 + 0.4 * sample)))


async def _dispatch_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    job = None
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            job = await uow.jobs.claim_next_due_dispatch(
                excluded_ids,
                claim_seconds=settings.worker_dispatch_claim_seconds,
            )
            if job is not None:
                claimed_ids.append(job.id)
    if job is None:
        return False

    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            asset = await uow.assets.get_asset_by_id(job.asset_id)
            source = await uow.sources.get_source_by_id(job.source_id)
            dispatcher = DispatchIngestionJobHandler(
                uow,
                HttpAIServiceIngestionGateway(),
                EventBus(),
                storage=S3ObjectStorage.from_settings,
                bucket=settings.object_storage_bucket,
            )

    claim_token = job.dispatch_claim_token
    if claim_token is None:
        raise RuntimeError(f"Claimed job {job.id} has no dispatch claim token.")
    if asset is None:
        outcome = DispatchAttemptOutcome(
            error_code="ASSET_NOT_FOUND",
            error_message=f"ContentAsset with id '{job.asset_id}' does not exist",
        )
    elif source is None:
        outcome = DispatchAttemptOutcome(
            error_code="CONTENT_SOURCE_NOT_FOUND",
            error_message=f"ContentSource with id '{job.source_id}' does not exist",
        )
    else:
        try:
            actor = SystemDispatchActor.for_job(job)
        except JobTenantMissing as exc:
            outcome = DispatchAttemptOutcome(error_code=exc.error_code, error_message=str(exc))
        else:
            outcome = await dispatcher.attempt_dispatch(
                job,
                asset,
                source,
                actor,
                claim_token=claim_token,
            )

    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            current = await uow.jobs.get_job_for_update(job.id)
            if (
                current is None
                or current.status != IngestionStatus.QUEUED
                or current.attempt_count != job.attempt_count
                or current.run_number != job.run_number
                or current.dispatch_claim_token != claim_token
            ):
                logger.info(
                    "content_job_dispatch_result_superseded",
                    job_id=job.id,
                    task_id=outcome.external_task_id,
                    run_number=job.run_number,
                    attempt=job.attempt_count,
                )
                return True
            current_asset = await uow.assets.get_asset_by_id(current.asset_id)
            result = await DispatchIngestionJobHandler(
                uow,
                HttpAIServiceIngestionGateway(),
                EventBus(),
                storage=S3ObjectStorage.from_settings,
                bucket=settings.object_storage_bucket,
            ).record_dispatch_outcome(
                current,
                current_asset,
                outcome,
                claim_token=claim_token,
            )
            logger.info(
                "content_job_dispatch_pass",
                job_id=result.id,
                task_id=result.external_task_id or outcome.external_task_id,
                run_number=result.run_number,
                attempt=result.attempt_count,
                status=result.status.value,
                outcome=("accepted" if outcome.external_task_id is not None else "uncertain" if outcome.uncertain else "failed"),
            )
            return True


async def _retry_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            job = await uow.jobs.claim_next_retryable_failure(excluded_ids)
            if job is None:
                return False
            claimed_ids.append(job.id)
            delay = retry_delay_seconds(
                job.attempt_count,
                settings.worker_retry_base_seconds,
                settings.worker_retry_cap_seconds,
            )
            job.schedule_retry(delay_seconds=delay)
            await uow.jobs.save_job(job)
            asset = await uow.assets.get_asset_by_id(job.asset_id)
            if asset is not None:
                asset.update_ingestion_status(IngestionStatus.QUEUED)
                await uow.assets.save_asset(asset)
            logger.info(
                "content_job_retry_scheduled",
                job_id=job.id,
                task_id=job.external_task_id,
                run_number=job.run_number,
                attempt=job.attempt_count,
                delay_seconds=delay,
            )
            return True


async def run_dispatch_pass(stop: asyncio.Event | None = None) -> None:
    excluded_ids: set[str] = set()
    processed = 0
    while processed < settings.worker_dispatch_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _dispatch_one(excluded_ids, claimed_ids)
        except Exception as exc:
            excluded_ids.update(claimed_ids)
            logger.error(
                "content_job_dispatch_error",
                job_id=claimed_ids[-1] if claimed_ids else None,
                error_type=type(exc).__name__,
            )
            if not claimed_ids:
                raise
            continue
        if not found:
            return
        excluded_ids.update(claimed_ids)
        processed += 1


async def run_retry_pass(stop: asyncio.Event | None = None) -> None:
    excluded_ids: set[str] = set()
    processed = 0
    while processed < settings.worker_retry_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _retry_one(excluded_ids, claimed_ids)
        except Exception as exc:
            excluded_ids.update(claimed_ids)
            logger.error(
                "content_job_retry_error",
                job_id=claimed_ids[-1] if claimed_ids else None,
                error_type=type(exc).__name__,
            )
            if not claimed_ids:
                raise
            continue
        if not found:
            return
        excluded_ids.update(claimed_ids)
        processed += 1


async def run_orphan_sweep_pass(stop: asyncio.Event | None = None) -> None:
    if stop is not None and stop.is_set():
        return
    await sweep_orphaned_objects(S3ObjectStorage.from_settings(), bucket=settings.object_storage_bucket)


def write_health_state(completed_at: dict[str, float], path: Path = HEALTH_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(completed_at, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def check_worker_health(now: float | None = None, path: Path = HEALTH_PATH) -> None:
    if not path.is_file():
        raise RuntimeError("worker health file is missing")
    state = json.loads(path.read_text(encoding="utf-8"))
    current = time.time() if now is None else now
    intervals = {
        "dispatch": settings.worker_dispatch_interval_seconds,
        "retry": settings.worker_retry_interval_seconds,
        "orphan_sweep": settings.worker_orphan_sweep_interval_seconds,
    }
    unhealthy = [name for name, interval in intervals.items() if name not in state or current - state[name] > 3 * interval]
    if unhealthy:
        raise RuntimeError(f"worker loops are overdue: {', '.join(unhealthy)}")


async def _run_loop(
    name: str,
    interval_seconds: int,
    pass_fn: Callable[[asyncio.Event], Awaitable[None]],
    stop: asyncio.Event,
    completed_at: dict[str, float],
) -> None:
    while not stop.is_set():
        started = time.monotonic()
        try:
            await pass_fn(stop)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("worker_loop_pass_failed", loop=name, error_type=type(exc).__name__)
        else:
            completed_at[name] = time.time()
            write_health_state(completed_at)
        remaining = max(0.0, interval_seconds - (time.monotonic() - started))
        if remaining == 0:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=remaining)
        except TimeoutError:
            pass


async def serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_: stop.set())

    completed_at: dict[str, float] = {}
    write_health_state(completed_at)
    workers = [
        asyncio.create_task(
            _run_loop(
                "dispatch",
                settings.worker_dispatch_interval_seconds,
                run_dispatch_pass,
                stop,
                completed_at,
            )
        ),
        asyncio.create_task(
            _run_loop(
                "retry",
                settings.worker_retry_interval_seconds,
                run_retry_pass,
                stop,
                completed_at,
            )
        ),
        asyncio.create_task(
            _run_loop(
                "orphan_sweep",
                settings.worker_orphan_sweep_interval_seconds,
                run_orphan_sweep_pass,
                stop,
                completed_at,
            )
        ),
    ]
    for worker in workers:
        worker.add_done_callback(lambda _: stop.set())
    try:
        await stop.wait()
        try:
            await asyncio.wait_for(asyncio.gather(*workers), timeout=settings.worker_shutdown_grace_seconds)
        except TimeoutError:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
    finally:
        if not stop.is_set():
            stop.set()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="P3-6 content ingestion worker")
    parser.add_argument("--check", action="store_true", help="fail if any worker loop is overdue")
    args = parser.parse_args()
    if args.check:
        check_worker_health()
        return
    asyncio.run(serve())


if __name__ == "__main__":
    main()
