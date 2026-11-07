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
from datetime import datetime, timezone
from pathlib import Path

import structlog
from prometheus_client import start_http_server
from sqlalchemy import func, or_, select

from app.application.assessment.attempt_handlers import finalize_attempt
from app.application.content.job_handlers import (
    DispatchIngestionJobHandler,
    RecoverIngestionJobHandler,
)
from app.core.config import settings
from app.core.metrics import (
    assessment_attempts_finalized_total,
    content_in_flight_cap_hits_total,
    content_jobs_due,
    content_oldest_due_job_age_seconds,
    content_recoveries_total,
    content_retries_scheduled_total,
    content_scans_total,
    content_scope_assignment_oldest_age_seconds,
    content_scope_assignments_pending,
    content_scope_deliveries_total,
    registry,
)
from app.db.session import SessionLocal, engine
from app.db.timeouts import set_transaction_timeouts
from app.domain.assessment.attempt import FinalizedBy
from app.domain.content.enums import IngestionStatus
from app.events.event_bus import EventBus
from app.infrastructure.assessment.unit_of_work import AssessmentUnitOfWork
from app.infrastructure.content.ai_gateway import HttpAIServiceIngestionGateway
from app.infrastructure.content.clamav import ClamdScanner, ScannerUnavailable
from app.infrastructure.content.orphan_sweeper import sweep_orphaned_objects
from app.infrastructure.content.s3_object_storage import S3ObjectStorage
from app.infrastructure.content.scan_repository import ScanClaim, SqlAlchemyScanRepository
from app.infrastructure.content.scope_assignments import SqlAlchemyScopeAssignmentRepository
from app.infrastructure.content.scope_gateway import HttpScopeAssignmentGateway, ScopeDeliveryError
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from app.infrastructure.db.models.content import ContentIngestionJobModel

logger = structlog.get_logger(__name__)
HEALTH_PATH = Path(os.getenv("WORKER_HEALTH_PATH", "/tmp/build-backend-worker-health.json"))
WORKER_METRICS_PORT = 9101
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


async def update_dispatch_queue_metrics() -> None:
    now = datetime.now(timezone.utc)
    stmt = select(func.count(), func.min(ContentIngestionJobModel.created_at)).where(
        ContentIngestionJobModel.status == IngestionStatus.QUEUED.value,
        or_(
            ContentIngestionJobModel.next_retry_at.is_(None),
            ContentIngestionJobModel.next_retry_at <= now,
        ),
    )
    async with SessionLocal() as session:
        await set_transaction_timeouts(session)
        due_count, oldest_created_at = (await session.execute(stmt)).one()
    content_jobs_due.set(due_count)
    age = (now - oldest_created_at).total_seconds() if oldest_created_at else 0
    content_oldest_due_job_age_seconds.set(max(0, age))


async def _dispatch_and_measure(stop: asyncio.Event) -> None:
    await run_dispatch_pass(stop)
    await update_dispatch_queue_metrics()


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


def _scanner() -> ClamdScanner | None:
    if not settings.clamav_host:
        return None
    return ClamdScanner(settings.clamav_host, settings.clamav_port, float(settings.scan_timeout_seconds), settings.scan_max_bytes)


def _scan_storage() -> S3ObjectStorage:
    return S3ObjectStorage.from_settings()


def _managed_key(claim: ScanClaim) -> str | None:
    """The object key, only if the row's storage_uri is exactly the managed one."""
    from app.application.content.upload import object_key, storage_uri_for

    key = object_key(claim.tenant_id, claim.asset_id, claim.content_sha256)
    return key if claim.storage_uri == storage_uri_for(settings.object_storage_bucket, key) else None


async def _scan_one(claimed_ids: list[str]) -> bool:
    """Scan one pending document (M3-D ruling 7). The claim takes a fence and a
    lease and is committed before the scan runs, so no transaction is held
    across it; the verdict is recorded only if this attempt still holds the
    fence. Anything short of a verdict leaves the document quarantined, to be
    tried again: the scan fails closed."""
    async with SessionLocal() as session:
        async with session.begin():
            await set_transaction_timeouts(session)
            claim = await SqlAlchemyScanRepository(session).claim_due(settings.scan_lease_seconds)
    if claim is None:
        return False
    claimed_ids.append(claim.asset_id)
    try:
        scanner = _scanner()
        if scanner is None:
            raise ScannerUnavailable("SCANNER_NOT_CONFIGURED")
        key = _managed_key(claim)
        if key is None:
            raise ScannerUnavailable("NOT_IN_MANAGED_STORAGE")
        data = await _scan_storage().get(key, expected_sha256=claim.content_sha256, max_bytes=settings.scan_max_bytes)
        verdict = await scanner.scan(data)
    except Exception as exc:
        code = exc.code if isinstance(exc, ScannerUnavailable) else getattr(exc, "error_code", type(exc).__name__)
        delay = retry_delay_seconds(claim.attempts, settings.worker_retry_base_seconds, settings.worker_retry_cap_seconds)
        async with SessionLocal() as session:
            async with session.begin():
                await SqlAlchemyScanRepository(session).defer(claim, delay)
        content_scans_total.labels(outcome="deferred").inc()
        logger.warning(
            "content_scan_deferred",
            asset_id=claim.asset_id,
            tenant_id=claim.tenant_id,
            attempt=claim.attempts,
            error_code=code,
            retry_in_seconds=delay,
        )
        return True
    async with SessionLocal() as session:
        async with session.begin():
            recorded = await SqlAlchemyScanRepository(session).record_verdict(
                claim, accepted=verdict.clean, scanner=verdict.scanner, signature_version=verdict.signature_version
            )
    outcome = ("accepted" if verdict.clean else "rejected") if recorded else "superseded"
    content_scans_total.labels(outcome=outcome).inc()
    # The signature name is for operators; the uploader is never told it.
    (logger.info if verdict.clean else logger.warning)(
        "content_scan_verdict",
        asset_id=claim.asset_id,
        tenant_id=claim.tenant_id,
        attempt=claim.attempts,
        outcome=outcome,
        scanner=verdict.scanner,
        signature_version=verdict.signature_version,
        signature=verdict.signature,
    )
    return True


async def run_scan_pass(stop: asyncio.Event | None = None) -> None:
    processed = 0
    while processed < settings.worker_scan_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _scan_one(claimed_ids)
        except Exception as exc:
            logger.error(
                "content_scan_pass_error",
                asset_id=claimed_ids[-1] if claimed_ids else None,
                error_type=type(exc).__name__,
            )
            if not claimed_ids:
                raise
            # Its lease lapses and a later pass takes it again.
            processed += 1
            continue
        if not found:
            return
        processed += 1


def _scope_gateway() -> HttpScopeAssignmentGateway:
    return HttpScopeAssignmentGateway(timeout_seconds=settings.worker_scope_timeout_seconds)


async def _deliver_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    """Deliver one due scope assignment, lowerings first. The row stays locked
    across one bounded AI call; it's settled only when the AI service returns
    its version or a higher one, and otherwise stays pending with backoff."""
    async with SessionLocal() as session:
        async with session.begin():
            await set_transaction_timeouts(session)
            outbox = SqlAlchemyScopeAssignmentRepository(session)
            row = await outbox.claim_due(excluded_ids)
            if row is None:
                return False
            claimed_ids.append(row.id)
            try:
                stored = await asyncio.wait_for(
                    _scope_gateway().assign(
                        tenant_id=row.tenant_id,
                        asset_id=row.asset_id,
                        scope=row.scope,
                        version=row.version,
                        correlation_id=row.id,
                    ),
                    timeout=settings.worker_scope_timeout_seconds + 1,
                )
            except (ScopeDeliveryError, TimeoutError) as exc:
                code = exc.code if isinstance(exc, ScopeDeliveryError) else "AI_SERVICE_TIMEOUT"
                delay = retry_delay_seconds(
                    row.attempts + 1, settings.worker_retry_base_seconds, settings.worker_retry_cap_seconds
                )
                await outbox.record_failure(row, code, delay)
                content_scope_deliveries_total.labels(outcome="failed").inc()
                log = logger.error if code == "ASSET_HELD_BY_ANOTHER_TENANT" else logger.warning
                log(
                    "content_scope_assignment_not_delivered",
                    assignment_id=row.id,
                    tenant_id=row.tenant_id,
                    asset_id=row.asset_id,
                    version=row.version,
                    lowers=row.lowers,
                    attempt=row.attempts + 1,
                    error_code=code,
                    retry_in_seconds=delay,
                )
                return True
            outcome = await outbox.settle(row, stored)
            content_scope_deliveries_total.labels(outcome=outcome).inc()
            logger.info(
                "content_scope_assignment_delivered",
                assignment_id=row.id,
                tenant_id=row.tenant_id,
                asset_id=row.asset_id,
                version=row.version,
                stored_version=stored,
                lowers=row.lowers,
                outcome=outcome,
            )
            return True


async def update_scope_backlog_metrics() -> None:
    async with SessionLocal() as session:
        backlog = await SqlAlchemyScopeAssignmentRepository(session).backlog()
    now = datetime.now(timezone.utc)
    seen = {lowers: (count, oldest) for lowers, count, oldest in backlog}
    for lowers in (True, False):
        count, oldest = seen.get(lowers, (0, None))
        label = "true" if lowers else "false"
        content_scope_assignments_pending.labels(lowers=label).set(count)
        content_scope_assignment_oldest_age_seconds.labels(lowers=label).set(
            max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
        )


async def run_scope_assignment_pass(stop: asyncio.Event | None = None) -> None:
    excluded_ids: set[str] = set()
    processed = 0
    while processed < settings.worker_scope_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _deliver_one(excluded_ids, claimed_ids)
        except Exception as exc:
            excluded_ids.update(claimed_ids)
            logger.error(
                "content_scope_assignment_pass_error",
                assignment_id=claimed_ids[-1] if claimed_ids else None,
                error_type=type(exc).__name__,
            )
            if not claimed_ids:
                raise
            continue
        if not found:
            break
        # Settled or deferred, a row isn't taken again in this pass.
        excluded_ids.update(claimed_ids)
        processed += 1
    await update_scope_backlog_metrics()


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
            content_retries_scheduled_total.inc()
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
            content_recoveries_total.labels(outcome=result.action).inc()
            if result.action == "timeout":
                content_in_flight_cap_hits_total.inc()
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


async def _finalize_one(excluded_ids: set[str], claimed_ids: list[str]) -> bool:
    async with SessionLocal() as session:
        async with AssessmentUnitOfWork(session) as uow:
            await set_transaction_timeouts(session)
            attempt = await uow.attempts.claim_next_expired(excluded_ids)
            if attempt is None:
                return False
            claimed_ids.append(attempt.id)
            await finalize_attempt(
                uow.attempts,
                uow.assessments,
                uow.attempt_answers,
                uow.attempt_results,
                attempt_id=attempt.id,
                tenant_id=attempt.tenant_id,
                user_id=attempt.user_id,
                finalized_by=FinalizedBy.DEADLINE,
            )
    assessment_attempts_finalized_total.inc()
    return True


async def run_attempt_finalizer_pass(stop: asyncio.Event | None = None) -> None:
    excluded_ids: set[str] = set()
    processed = 0
    while processed < settings.worker_attempt_finalizer_batch and not (stop and stop.is_set()):
        claimed_ids: list[str] = []
        try:
            found = await _finalize_one(excluded_ids, claimed_ids)
        except Exception as exc:
            # Rolled back, so it stays eligible for the next pass and for a read.
            excluded_ids.update(claimed_ids)
            logger.error(
                "assessment_attempt_finalize_error",
                attempt_id=claimed_ids[-1] if claimed_ids else None,
                error_type=type(exc).__name__,
            )
            if not claimed_ids:
                raise
            continue
        if not found:
            return
        excluded_ids.update(claimed_ids)
        processed += 1


async def run_registration_pass(stop: asyncio.Event | None = None) -> None:
    # Imported here: the other loops don't need the identity services built.
    from app.application.identity.user_service import UserService
    from app.bootstrap.container import build_container

    await build_container().get(UserService).process_pending_registrations(stop)


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


def check_worker_health(now: float | None = None, path: Path = HEALTH_PATH, *, registrations: bool = False) -> None:
    if not path.is_file():
        raise RuntimeError("worker health file is missing")
    state = json.loads(path.read_text(encoding="utf-8"))
    current = time.time() if now is None else now
    intervals = (
        {"registrations": settings.worker_registration_interval_seconds}
        if registrations
        else {
            "dispatch": settings.worker_dispatch_interval_seconds,
            "retry": settings.worker_retry_interval_seconds,
            "orphan_sweep": settings.worker_orphan_sweep_interval_seconds,
            "recoverer": settings.worker_recoverer_interval_seconds,
            "attempt_finalizer": settings.worker_attempt_finalizer_interval_seconds,
        }
    )
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


def _registration_loops(stop: asyncio.Event, completed_at: dict[str, float]) -> list[asyncio.Task[None]]:
    interval = settings.worker_registration_interval_seconds
    return [asyncio.create_task(_run_loop("registrations", interval, run_registration_pass, stop, completed_at))]


async def serve(*, registrations: bool = False) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_: stop.set())

    completed_at: dict[str, float] = {}
    write_health_state(completed_at)
    metrics_server, _ = start_http_server(WORKER_METRICS_PORT, registry=registry)
    workers = (
        _registration_loops(stop, completed_at)
        if registrations
        else [
            asyncio.create_task(
                _run_loop(
                    "dispatch",
                    settings.worker_dispatch_interval_seconds,
                    _dispatch_and_measure,
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
            asyncio.create_task(
                _run_loop(
                    "scans",
                    settings.worker_scan_interval_seconds,
                    run_scan_pass,
                    "scope_assignments",
                    settings.worker_scope_interval_seconds,
                    run_scope_assignment_pass,
                    stop,
                    completed_at,
                )
            ),
            asyncio.create_task(
                _run_loop(
                    "attempt_finalizer",
                    settings.worker_attempt_finalizer_interval_seconds,
                    run_attempt_finalizer_pass,
                    stop,
                    completed_at,
                )
            ),
        ]
    )
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
        metrics_server.shutdown()
        metrics_server.server_close()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="P3-6 content ingestion worker")
    parser.add_argument("--check", action="store_true", help="fail if any worker loop is overdue")
    parser.add_argument(
        "--registrations",
        action="store_true",
        help="run only the registration loop: its own process, so it can't slow a request or stop with the others",
    )
    args = parser.parse_args()
    if args.check:
        check_worker_health(registrations=args.registrations)
        return
    asyncio.run(serve(registrations=args.registrations))


if __name__ == "__main__":
    main()
