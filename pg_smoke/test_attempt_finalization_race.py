"""Finalization and deadlines on real PostgreSQL: the submit lock, the shared
lock with saves, the worker, and the one clock. Where a lock or a clock choice
is what provides the guarantee, the same order also runs without it."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app import worker
from app.application.assessment.attempt_answer_commands import SaveAttemptAnswerCommand
from app.application.assessment.attempt_answer_handlers import SaveAttemptAnswerHandler
from app.application.assessment.attempt_commands import SubmitAttemptCommand
from app.application.assessment.attempt_handlers import SubmitAttemptHandler
from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.db.session import SessionLocal
from app.domain.assessment import attempt as attempt_module
from app.domain.assessment.errors import AttemptAlreadySubmittedError, AttemptExpiredError
from app.infrastructure.assessment.repositories import (
    SqlAlchemyAssessmentRepository,
    SqlAlchemyAttemptAnswerRepository,
    SqlAlchemyAttemptRepository,
    SqlAlchemyAttemptResultRepository,
)
from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentAttemptResultModel
from pg_smoke.test_attempt_policy_race import _assessment, _student

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _started(client):
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment()
    attempt = await build_container().get(AttemptService).start_attempt(assessment_id, tenant_id, user_id)
    return tenant_id, user_id, attempt.id


async def _expire(attempt_id: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(AssessmentAttemptModel)
            .where(AssessmentAttemptModel.id == attempt_id)
            .values(expires_at=func.clock_timestamp() - timedelta(minutes=1))
        )
        await session.commit()


async def _results(attempt_id: str) -> int:
    async with SessionLocal() as session:
        statement = select(func.count()).where(AssessmentAttemptResultModel.attempt_id == attempt_id)
        return (await session.execute(statement)).scalar_one()


async def _stored(attempt_id: str) -> AssessmentAttemptModel:
    async with SessionLocal() as session:
        return (await session.scalars(select(AssessmentAttemptModel).where(AssessmentAttemptModel.id == attempt_id))).one()


def _submit_handler(session, attempts) -> SubmitAttemptHandler:
    return SubmitAttemptHandler(
        attempts,
        SqlAlchemyAssessmentRepository(session),
        SqlAlchemyAttemptAnswerRepository(session),
        SqlAlchemyAttemptResultRepository(session),
    )


class PausesAfterRead(SqlAlchemyAttemptRepository):
    def __init__(self, session, has_read: asyncio.Event, resume: asyncio.Event) -> None:
        super().__init__(session)
        self.has_read, self.resume = has_read, resume

    async def get_by_id_for_update(self, attempt_id, tenant_id=None, user_id=None):
        attempt = await super().get_by_id_for_update(attempt_id, tenant_id, user_id)
        self.has_read.set()
        await self.resume.wait()
        return attempt


class NoRowLock(SqlAlchemyAttemptRepository):
    async def get_by_id_for_update(self, attempt_id, tenant_id=None, user_id=None):
        return await self.get_by_id(attempt_id, tenant_id, user_id)


class PausesWithoutLock(PausesAfterRead):
    async def get_by_id_for_update(self, attempt_id, tenant_id=None, user_id=None):
        attempt = await self.get_by_id(attempt_id, tenant_id, user_id)
        self.has_read.set()
        await self.resume.wait()
        return attempt


async def _slow_submit_against_fast(slow_class, fast_class, tenant_id, user_id, attempt_id):
    has_read, resume = asyncio.Event(), asyncio.Event()
    command = SubmitAttemptCommand(attempt_id, tenant_id, user_id)

    async def slow():
        async with SessionLocal() as session:
            await _submit_handler(session, slow_class(session, has_read, resume)).handle(command)
            await session.commit()

    async def fast():
        await has_read.wait()
        async with SessionLocal() as session:
            await _submit_handler(session, fast_class(session)).handle(command)
            await session.commit()

    slow_task, fast_task = asyncio.create_task(slow()), asyncio.create_task(fast())
    await has_read.wait()
    done, _ = await asyncio.wait({fast_task}, timeout=1.0)
    finished_while_paused = bool(done)
    resume.set()
    outcomes = await asyncio.gather(slow_task, fast_task, return_exceptions=True)
    return finished_while_paused, outcomes


async def test_the_submit_lock_makes_a_second_submit_wait(client):
    tenant_id, user_id, attempt_id = await _started(client)

    finished_while_paused, outcomes = await _slow_submit_against_fast(
        PausesAfterRead, SqlAlchemyAttemptRepository, tenant_id, user_id, attempt_id
    )

    assert finished_while_paused is False
    assert outcomes == [None, None]
    assert await _results(attempt_id) == 1


async def test_without_the_submit_lock_both_grade_and_one_hits_the_constraint(client):
    # #54's lock, shown necessary. The unique constraint still protects the
    # data, but the student's second request fails with an error.
    tenant_id, user_id, attempt_id = await _started(client)

    finished_while_paused, outcomes = await _slow_submit_against_fast(
        PausesWithoutLock, NoRowLock, tenant_id, user_id, attempt_id
    )

    assert finished_while_paused is True
    assert isinstance(outcomes[0], IntegrityError)
    assert await _results(attempt_id) == 1


async def test_a_student_and_the_worker_at_once_grade_once(client):
    tenant_id, user_id, attempt_id = await _started(client)
    await _expire(attempt_id)
    service = build_container().get(AttemptService)

    await asyncio.gather(
        service.submit_attempt(attempt_id, tenant_id, user_id),
        worker.run_attempt_finalizer_pass(),
        service.get_attempt(attempt_id, tenant_id, user_id),
    )

    assert (await _stored(attempt_id)).status == "submitted"
    assert await _results(attempt_id) == 1


async def test_two_workers_never_finalize_one_attempt_twice(client):
    attempts = [await _started(client) for _ in range(8)]
    for _, _, attempt_id in attempts:
        await _expire(attempt_id)

    await asyncio.gather(*(worker.run_attempt_finalizer_pass() for _ in range(4)))

    for _, _, attempt_id in attempts:
        assert (await _stored(attempt_id)).finalized_by == "deadline"
        assert await _results(attempt_id) == 1


async def test_the_worker_skips_a_row_someone_else_is_finalizing(client):
    _, _, attempt_id = await _started(client)
    await _expire(attempt_id)
    async with SessionLocal() as holder:
        await holder.execute(select(AssessmentAttemptModel).where(AssessmentAttemptModel.id == attempt_id).with_for_update())

        # Returns rather than waits, and leaves it for later.
        await asyncio.wait_for(worker.run_attempt_finalizer_pass(), timeout=10)
        assert await _results(attempt_id) == 0
        await holder.rollback()

    await worker.run_attempt_finalizer_pass()
    assert await _results(attempt_id) == 1


async def test_a_save_waits_for_finalization_and_is_then_refused(client):
    # An answer is committed before grading, or refused. Never lost in between.
    tenant_id, user_id, attempt_id = await _started(client)
    await _expire(attempt_id)
    has_read, resume = asyncio.Event(), asyncio.Event()

    async def finalize():
        async with SessionLocal() as session:
            await _submit_handler(session, PausesAfterRead(session, has_read, resume)).handle(
                SubmitAttemptCommand(attempt_id, tenant_id, user_id)
            )
            await session.commit()

    async def save():
        await has_read.wait()
        async with SessionLocal() as session:
            await SaveAttemptAnswerHandler(
                SqlAlchemyAttemptRepository(session),
                SqlAlchemyAssessmentRepository(session),
                SqlAlchemyAttemptAnswerRepository(session),
            ).handle(SaveAttemptAnswerCommand(attempt_id, "question", 0, tenant_id, user_id))

    finalize_task, save_task = asyncio.create_task(finalize()), asyncio.create_task(save())
    await has_read.wait()
    done, _ = await asyncio.wait({save_task}, timeout=1.0)
    assert not done  # waiting on the same row lock
    resume.set()
    await finalize_task
    with pytest.raises(AttemptAlreadySubmittedError):
        await save_task


class TransactionClock(SqlAlchemyAttemptRepository):
    """now() instead of clock_timestamp(): the transaction's start."""

    async def database_now(self):
        return (await self._session.execute(select(func.now()))).scalar_one()


async def _save_after_waiting_past_the_deadline(attempts_class, client):
    """The save's transaction starts before the deadline, and waits on the row
    lock until after it."""
    tenant_id, user_id, attempt_id = await _started(client)
    async with SessionLocal() as session:
        await session.execute(
            update(AssessmentAttemptModel)
            .where(AssessmentAttemptModel.id == attempt_id)
            .values(expires_at=func.clock_timestamp() + timedelta(seconds=1))
        )
        await session.commit()

    holder = SessionLocal()
    await holder.execute(select(AssessmentAttemptModel).where(AssessmentAttemptModel.id == attempt_id).with_for_update())
    in_transaction = asyncio.Event()

    async def save():
        async with SessionLocal() as session:
            await session.execute(text("SELECT now()"))
            in_transaction.set()
            await SaveAttemptAnswerHandler(
                attempts_class(session), SqlAlchemyAssessmentRepository(session), SqlAlchemyAttemptAnswerRepository(session)
            ).handle(SaveAttemptAnswerCommand(attempt_id, "question", 0, tenant_id, user_id))

    task = asyncio.create_task(save())
    await in_transaction.wait()
    await asyncio.sleep(1.5)
    await holder.rollback()
    await holder.close()
    return task


async def test_a_save_that_waited_past_the_deadline_is_refused(client):
    task = await _save_after_waiting_past_the_deadline(SqlAlchemyAttemptRepository, client)
    with pytest.raises(AttemptExpiredError):
        await task


async def test_with_the_transaction_clock_the_same_save_passes_the_deadline(client):
    # Why it's clock_timestamp(). The save gets past the deadline check, then
    # stops at the question lookup, since this assessment has no questions.
    task = await _save_after_waiting_past_the_deadline(TransactionClock, client)
    with pytest.raises(LookupError):
        await task


class FutureDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2099, 1, 1, tzinfo=timezone.utc)


async def test_deadlines_ignore_the_application_clock(client, monkeypatch):
    # A server whose clock is far ahead: the attempt must start and stay running.
    monkeypatch.setattr(attempt_module, "datetime", FutureDatetime)
    tenant_id, user_id, attempt_id = await _started(client)

    stored = await _stored(attempt_id)
    assert stored.started_at.year < 2099
    assert stored.expires_at - stored.started_at == timedelta(minutes=30)

    await worker.run_attempt_finalizer_pass()
    fetched = await build_container().get(AttemptService).get_attempt(attempt_id, tenant_id, user_id)
    assert fetched.status.value == "in_progress"
