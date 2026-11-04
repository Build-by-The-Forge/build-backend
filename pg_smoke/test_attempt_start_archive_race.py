"""Starting an attempt against archiving its course, on real PostgreSQL (M3-E).

A start reads the course, its department and its faculty FOR SHARE inside
L1's transaction, so an archive can't commit between the check and the
insert. These tests force both orders, and show that a start either commits
before the archive, or sees it and takes no attempt.
"""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.application.assessment.attempt_commands import StartAttemptCommand
from app.application.assessment.attempt_handlers import StartAttemptHandler
from app.db.session import SessionLocal
from app.domain.client_safe import ClientSafeError
from app.infrastructure.assessment.repositories import SqlAlchemyAssessmentRepository, SqlAlchemyAttemptRepository
from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentModel
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import DepartmentModel
from pg_smoke.test_attempt_policy_race import _assessment

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _course_and_department(assessment_id: str) -> tuple[str, str]:
    async with SessionLocal() as session:
        course_id = await session.scalar(select(AssessmentModel.course_id).where(AssessmentModel.id == assessment_id))
        department_id = await session.scalar(select(CourseModel.department_id).where(CourseModel.id == course_id))
    return course_id, department_id


def _archive(level: str, course_id: str, department_id: str):
    if level == "course":
        return update(CourseModel).where(CourseModel.id == course_id).values(status="archived")
    return update(DepartmentModel).where(DepartmentModel.id == department_id).values(status="archived")


@pytest.mark.parametrize("level", ["course", "department"])
async def test_an_archive_waits_for_a_start_holding_the_course(level):
    tenant_id, assessment_id = await _assessment()
    course_id, department_id = await _course_and_department(assessment_id)
    async with SessionLocal() as starting, starting.begin():
        assert await SqlAlchemyAttemptRepository(starting).lock_course_open(course_id, tenant_id)
        # The start's transaction is still open: the archive can't commit.
        async with SessionLocal() as archiving:
            with pytest.raises(DBAPIError, match="lock timeout|lock_not_available|canceling statement"):
                async with archiving.begin():
                    await archiving.execute(text("SET LOCAL lock_timeout = '300ms'"))
                    await archiving.execute(_archive(level, course_id, department_id))


@pytest.mark.parametrize("level", ["course", "department"])
async def test_a_start_waiting_on_an_archive_sees_it_and_takes_no_attempt(level):
    tenant_id, assessment_id = await _assessment()
    course_id, department_id = await _course_and_department(assessment_id)
    async with SessionLocal() as archiving:
        await archiving.begin()
        await archiving.execute(_archive(level, course_id, department_id))  # uncommitted

        async def start() -> bool:
            async with SessionLocal() as starting, starting.begin():
                return await SqlAlchemyAttemptRepository(starting).lock_course_open(course_id, tenant_id)

        waiting = asyncio.create_task(start())
        await asyncio.sleep(0.5)
        assert not waiting.done(), "the start must wait for the archive's row lock"
        await archiving.commit()
        assert await asyncio.wait_for(waiting, timeout=10) is False


async def test_a_start_after_an_archive_is_refused_and_inserts_nothing():
    # Through the whole handler, past five runs, where a cached plan could differ.
    tenant_id, assessment_id = await _assessment()
    course_id, department_id = await _course_and_department(assessment_id)
    async with SessionLocal() as session, session.begin():
        await session.execute(_archive("course", course_id, department_id))
    for _ in range(7):
        # Refused before any insert, so no user row is needed.
        user_id = str(uuid4())
        async with SessionLocal() as session, session.begin():
            handler = StartAttemptHandler(SqlAlchemyAttemptRepository(session), SqlAlchemyAssessmentRepository(session))
            with pytest.raises(ClientSafeError, match="not available for attempts"):
                await handler.handle(StartAttemptCommand(assessment_id, tenant_id, user_id))
    async with SessionLocal() as session:
        found = await session.scalar(
            select(AssessmentAttemptModel.id).where(AssessmentAttemptModel.assessment_id == assessment_id).limit(1)
        )
    assert found is None
