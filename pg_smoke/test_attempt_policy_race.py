"""What protects the attempt limit and the policy lock, on real PostgreSQL.

The unique index can't protect the limit: a slow start can count attempts, then
wait while a faster one starts and submits. Nothing is in progress any more, so
its insert succeeds on the stale count. These tests force that order, and show
the outcome both with the lock and without it, so they can't pass by accident.
"""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.application.assessment.assessment_commands import PublishAssessmentCommand, UpdateAssessmentCommand
from app.application.assessment.assessment_handlers import PublishAssessmentHandler, UpdateAssessmentHandler
from app.application.assessment.attempt_commands import StartAttemptCommand, SubmitAttemptCommand
from app.application.assessment.attempt_handlers import StartAttemptHandler, SubmitAttemptHandler
from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.db.session import SessionLocal
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.attempt_policy import AttemptPolicy
from app.domain.assessment.errors import AttemptPolicyLockedError
from app.infrastructure.assessment.repositories import SqlAlchemyAssessmentRepository, SqlAlchemyAttemptRepository
from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentModel
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import DepartmentModel, FacultyModel, TenantModel

pytestmark = pytest.mark.asyncio(loop_scope="session")

ONE_ATTEMPT = {"max_attempts": 1, "retake_after_submission": False}


async def _assessment(*, status="published", **policy) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    stamps = {"status": "active", "created_at": now, "updated_at": now}
    tenant_id, faculty_id, department_id, course_id, assessment_id = (str(uuid4()) for _ in range(5))
    tag = uuid4().hex[:8]
    rows = [
        TenantModel(id=tenant_id, name="Race", slug=f"race-{tag}", **stamps),
        FacultyModel(id=faculty_id, tenant_id=tenant_id, name="Race", slug=f"f-{tag}", **stamps),
        DepartmentModel(
            id=department_id, tenant_id=tenant_id, faculty_id=faculty_id, name="Race", slug=f"d-{tag}", code=f"D{tag}", **stamps
        ),
        CourseModel(
            id=course_id,
            tenant_id=tenant_id,
            department_id=department_id,
            code=f"C{tag}",
            title="Race",
            slug=f"c-{tag}",
            credit_units=3,
            level=100,
            semester=1,
            status="published",
            created_at=now,
            updated_at=now,
        ),
        AssessmentModel(
            id=assessment_id,
            tenant_id=tenant_id,
            course_id=course_id,
            title="Race",
            instructions="Answer.",
            duration_minutes=30,
            passing_score=0,
            status=status,
            created_at=now,
            updated_at=now,
            **policy,
        ),
    ]
    async with SessionLocal() as session:
        for row in rows:  # one at a time, parents first, for the foreign keys
            session.add(row)
            await session.flush()
        await session.commit()
    return tenant_id, assessment_id


async def _student(client) -> str:
    registered = await client.post(
        "/identity/users", json={"email": f"race-{uuid4()}@example.com", "password": "Correct-Horse-Battery-9"}
    )
    assert registered.status_code == 201, registered.text
    return registered.json()["data"]["id"]


async def _attempt_count(assessment_id: str) -> int:
    async with SessionLocal() as session:
        statement = select(func.count()).where(AssessmentAttemptModel.assessment_id == assessment_id)
        return (await session.execute(statement)).scalar_one()


class PausesAfterCounting(SqlAlchemyAttemptRepository):
    """Holds the slow start between its count and its insert."""

    def __init__(self, session, counted: asyncio.Event, resume: asyncio.Event) -> None:
        super().__init__(session)
        self.counted, self.resume = counted, resume

    async def count_for_user(self, assessment_id, user_id, tenant_id):
        used = await super().count_for_user(assessment_id, user_id, tenant_id)
        self.counted.set()
        await self.resume.wait()
        return used


class NoLock(SqlAlchemyAttemptRepository):
    async def lock_starts(self, assessment_id, user_id, tenant_id):
        return None


class PausesWithoutLock(PausesAfterCounting, NoLock):
    pass


async def _slow_against_fast(repository_class, fast_repository_class, tenant_id, assessment_id, user_id) -> bool:
    """The slow start counts and pauses; a fast start-and-submit runs. Returns
    whether the fast one finished while the slow one was paused."""
    counted, resume = asyncio.Event(), asyncio.Event()
    command = StartAttemptCommand(assessment_id, tenant_id, user_id)

    async def slow():
        async with SessionLocal() as session:
            attempts = repository_class(session, counted, resume)
            await StartAttemptHandler(attempts, SqlAlchemyAssessmentRepository(session)).handle(command)
            await session.commit()

    async def fast():
        await counted.wait()
        async with SessionLocal() as session:
            attempts = fast_repository_class(session)
            attempt = await StartAttemptHandler(attempts, SqlAlchemyAssessmentRepository(session)).handle(command)
            if attempt is not None:
                await SubmitAttemptHandler(attempts).handle(SubmitAttemptCommand(attempt.id, tenant_id, user_id))
            await session.commit()

    slow_task, fast_task = asyncio.create_task(slow()), asyncio.create_task(fast())
    await counted.wait()
    done, _ = await asyncio.wait({fast_task}, timeout=1.0)
    finished_while_paused = bool(done)
    resume.set()
    await asyncio.gather(slow_task, fast_task)
    return finished_while_paused


async def test_a_slow_start_cannot_exceed_the_limit_with_the_lock(client):
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment(**ONE_ATTEMPT)

    finished_while_paused = await _slow_against_fast(
        PausesAfterCounting, SqlAlchemyAttemptRepository, tenant_id, assessment_id, user_id
    )

    assert finished_while_paused is False  # the fast start waited on the lock
    assert await _attempt_count(assessment_id) == 1


async def test_without_the_lock_the_same_order_exceeds_the_limit(client):
    # The lock's failure case, kept as a test: this is what the test above rules out.
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment(**ONE_ATTEMPT)

    finished_while_paused = await _slow_against_fast(PausesWithoutLock, NoLock, tenant_id, assessment_id, user_id)

    assert finished_while_paused is True
    assert await _attempt_count(assessment_id) == 2


async def test_simultaneous_starts_get_one_attempt(client):
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment(**ONE_ATTEMPT)
    service = build_container().get(AttemptService)

    attempts = await asyncio.gather(*(service.start_attempt(assessment_id, tenant_id, user_id) for _ in range(5)))

    assert len({attempt.id for attempt in attempts}) == 1
    assert await _attempt_count(assessment_id) == 1


async def test_without_the_lock_on_conflict_still_gives_one_attempt_and_no_error(client):
    # ON CONFLICT is the defence for a path without the lock: a uniqueness
    # violation would leave the transaction failed.
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment()
    command = StartAttemptCommand(assessment_id, tenant_id, user_id)

    async def start():
        async with SessionLocal() as session:
            handler = StartAttemptHandler(NoLock(session), SqlAlchemyAssessmentRepository(session))
            attempt = await handler.handle(command)
            await session.commit()
            return attempt

    attempts = await asyncio.gather(*(start() for _ in range(5)))

    assert await _attempt_count(assessment_id) == 1
    assert all(attempt is not None for attempt in attempts)


async def test_repeated_starts_on_one_connection_keep_working(client):
    # PostgreSQL moves a prepared statement to a generic plan after five runs,
    # and a bound partial-index predicate can't be matched there. Pooled
    # connections reuse statements, so this failed only after some traffic.
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment()
    async with SessionLocal() as session:
        attempts = SqlAlchemyAttemptRepository(session)
        outcomes = [
            await attempts.insert_unless_active(
                AssessmentAttempt.start(tenant_id=tenant_id, assessment_id=assessment_id, user_id=user_id, duration_minutes=30)
            )
            for _ in range(12)
        ]
        await session.commit()
    assert outcomes == [True] + [False] * 11
    assert await _attempt_count(assessment_id) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"max_attempts": 1, "retake_after_submission": True},
        {"max_attempts": None, "retake_after_submission": False},
        {"max_attempts": 2, "retake_after_submission": False},
        {"feedback_timing": "after_final_attempt"},
        {"attempt_kind": "exam"},
        {"scoring_policy": "average"},
    ],
)
async def test_the_database_refuses_a_contradictory_policy(values):
    # Past the domain entirely, as a future path or a manual fix might go.
    _, assessment_id = await _assessment()
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    async with SessionLocal() as session:
        with pytest.raises(Exception, match="ck_assessments_"):
            await session.execute(text(f"UPDATE assessments SET {assignments} WHERE id = :id"), {**values, "id": assessment_id})
        await session.rollback()


class SlowRead(SqlAlchemyAssessmentRepository):
    """Holds an edit after it has read the assessment, before it writes."""

    def __init__(self, session, has_read: asyncio.Event, resume: asyncio.Event) -> None:
        super().__init__(session)
        self.has_read, self.resume = has_read, resume

    async def get_by_id(self, assessment_id, tenant_id=None):
        assessment = await super().get_by_id(assessment_id, tenant_id)
        self.has_read.set()
        await self.resume.wait()
        return assessment


class SlowReadNoLock(SlowRead):
    async def lock_for_change(self, assessment_id, tenant_id):
        return None


async def _edit_against_publish(repository_class, tenant_id, assessment_id, policy):
    has_read, resume = asyncio.Event(), asyncio.Event()

    async def edit():
        async with SessionLocal() as session:
            handler = UpdateAssessmentHandler(repository_class(session, has_read, resume))
            await handler.handle(UpdateAssessmentCommand(assessment_id, tenant_id, attempt_policy=policy))
            await session.commit()

    async def publish():
        await has_read.wait()
        async with SessionLocal() as session:
            repository = SqlAlchemyAssessmentRepository(session)
            await repository.lock_for_change(assessment_id, tenant_id)
            await session.execute(text("UPDATE assessments SET status = 'published' WHERE id = :id"), {"id": assessment_id})
            await session.commit()

    edit_task, publish_task = asyncio.create_task(edit()), asyncio.create_task(publish())
    await has_read.wait()
    done, _ = await asyncio.wait({publish_task}, timeout=1.0)
    published_while_paused = bool(done)
    resume.set()
    await asyncio.gather(edit_task, publish_task)
    return published_while_paused


async def _stored_max_attempts(assessment_id: str) -> int | None:
    async with SessionLocal() as session:
        return (await session.scalars(select(AssessmentModel.max_attempts).where(AssessmentModel.id == assessment_id))).one()


async def _stored_status(assessment_id: str) -> str:
    async with SessionLocal() as session:
        return (await session.scalars(select(AssessmentModel.status).where(AssessmentModel.id == assessment_id))).one()


def _limited_policy() -> AttemptPolicy:
    return replace(AttemptPolicy.practice_default(), max_attempts=3)


async def test_an_edit_that_read_a_draft_holds_off_publication(client):
    # The edit holds the row, so publishing waits and the edit lands on a draft.
    tenant_id, assessment_id = await _assessment(status="draft")

    published_while_paused = await _edit_against_publish(SlowRead, tenant_id, assessment_id, _limited_policy())

    assert published_while_paused is False
    assert await _stored_max_attempts(assessment_id) == 3
    assert await _stored_status(assessment_id) == "published"


async def test_without_the_lock_an_edit_changes_a_policy_after_publication(client):
    # The failure the lock rules out: published first, then the stale edit
    # writes its policy and its copy of the status, undoing the publication.
    tenant_id, assessment_id = await _assessment(status="draft")

    published_while_paused = await _edit_against_publish(SlowReadNoLock, tenant_id, assessment_id, _limited_policy())

    assert published_while_paused is True
    assert await _stored_max_attempts(assessment_id) == 3
    assert await _stored_status(assessment_id) == "draft"


async def test_an_edit_arriving_after_publication_is_refused(client):
    tenant_id, assessment_id = await _assessment(status="draft")
    async with SessionLocal() as session:
        await session.execute(text("UPDATE assessments SET status = 'published' WHERE id = :id"), {"id": assessment_id})
        await session.commit()

    async with SessionLocal() as session:
        handler = UpdateAssessmentHandler(SqlAlchemyAssessmentRepository(session))
        with pytest.raises(AttemptPolicyLockedError):
            await handler.handle(UpdateAssessmentCommand(assessment_id, tenant_id, attempt_policy=_limited_policy()))
        await session.rollback()

    assert await _stored_max_attempts(assessment_id) is None


async def test_publish_waits_for_an_edit_holding_the_row(client):
    tenant_id, assessment_id = await _assessment(status="draft")
    async with SessionLocal() as holder:
        await SqlAlchemyAssessmentRepository(holder).lock_for_change(assessment_id, tenant_id)

        async def publish():
            async with SessionLocal() as session:
                try:
                    await PublishAssessmentHandler(SqlAlchemyAssessmentRepository(session)).handle(
                        PublishAssessmentCommand(assessment_id, tenant_id)
                    )
                except ValueError:
                    pass  # this assessment has no questions: reaching publish() is the point
                await session.rollback()

        task = asyncio.create_task(publish())
        done, _ = await asyncio.wait({task}, timeout=0.5)
        assert not done
        await holder.rollback()
    await task
