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

from app.application.content.job_handlers import (
    DispatchIngestionJobHandler,
    RecoverIngestionJobHandler,
)
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.db.timeouts import set_transaction_timeouts
from app.domain.content.enums import IngestionStatus
from app.events.event_bus import EventBus
from app.infrastructure.content.ai_gateway import HttpAIServiceIngestionGateway
from app.infrastructure.content.orphan_sweeper import sweep_orphaned_objects
from app.infrastructure.content.s3_object_storage import S3ObjectStorage
from app.infrastructure.content.unit_of_work import ContentUnitOfWork

logger = structlog.get_logger(__name__)
HEALTH_PATH = Path(os.getenv("WORKER_HEALTH_PATH", "/tmp/build-backend-worker-health.json"))
# The storage check that precedes a dispatch also runs under the job's row
# lock (design §4), so it gets short bounds of its own.
DISPATCH_STORAGE_CONNECT_SECONDS = 2.0
DISPATCH_STORAGE_READ_SECONDS = 3.0


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


def _dispatch_gateway() -> HttpAIServiceIngestionGateway:
    return HttpAIServiceIngestionGateway(timeout_seconds=settings.worker_dispatch_timeout_seconds)


def _dispatch_storage() -> S3ObjectStorage:
    return S3ObjectStorage.from_settings(
        settings.model_copy(
            update={
                "object_storage_connect_timeout_seconds": DISPATCH_STORAGE_CONNECT_SECONDS,
                "object_storage_read_timeout_seconds": DISPATCH_STORAGE_READ_SECONDS,
            }
        )
    )


def dispatch_lock_bound_seconds() -> float:
    """The longest the dispatch step may hold the job's row lock: the
    storage check plus the AI call. Past it, the step is cancelled and its
    transaction rolls back; the job stays queued on the same attempt and
    key, so the next pass gets the original task back as DUPLICATE."""
    return DISPATCH_STORAGE_CONNECT_SECONDS + DISPATCH_STORAGE_READ_SECONDS + settings.worker_dispatch_timeout_seconds


async def _dispatch_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            job = await uow.jobs.claim_next_due_dispatch(excluded_ids)
            if job is None:
                return False
            claimed_ids.append(job.id)
            # Design §4: this transaction locks exactly this row, across one
            # bounded storage check and one bounded AI call, never AI work.
            await asyncio.wait_for(
                DispatchIngestionJobHandler(
                    uow,
                    _dispatch_gateway(),
                    EventBus(),
                    storage=_dispatch_storage,
                    bucket=settings.object_storage_bucket,
                ).handle_system(job),
                timeout=dispatch_lock_bound_seconds(),
            )
            logger.info(
                "content_job_dispatch_pass",
                job_id=job.id,
                task_id=job.external_task_id,
                run_number=job.run_number,
                attempt=job.attempt_count,
                status=job.status.value,
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


async def _recover_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            job = await uow.jobs.claim_next_overdue_job(
                excluded_ids,
                processing_seconds=settings.worker_stuck_processing_seconds,
                stage_seconds=settings.worker_stuck_stage_seconds,
                max_in_flight_seconds=settings.worker_max_in_flight_seconds,
            )
            if job is None:
                return False
            claimed_ids.append(job.id)
            result = await RecoverIngestionJobHandler(
                uow,
                HttpAIServiceIngestionGateway(),
                EventBus(),
            ).handle(
                job,
                max_in_flight_seconds=settings.worker_max_in_flight_seconds,
            )
            logger.info(
                "content_job_recovery_pass",
                job_id=result.job.id,
                task_id=result.job.external_task_id,
                run_number=result.job.run_number,
                attempt=result.job.attempt_count,
                outcome=result.action,
                status=result.job.status.value,
                callback_outcomes=result.callback_outcomes,
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


async def run_recoverer_pass(stop: asyncio.Event | None = None) -> None:
    excluded_ids: set[str] = set()
    processed = 0
    while processed < settings.worker_recoverer_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _recover_one(excluded_ids, claimed_ids)
        except Exception as exc:
            excluded_ids.update(claimed_ids)
            logger.error(
                "content_job_recovery_error",
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
        "recoverer": settings.worker_recoverer_interval_seconds,
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
        asyncio.create_task(
            _run_loop(
                "recoverer",
                settings.worker_recoverer_interval_seconds,
                run_recoverer_pass,
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
