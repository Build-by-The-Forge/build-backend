import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.infrastructure.assessment.repositories import SqlAlchemyAttemptRepository


@pytest.mark.asyncio
async def test_attempt_round_trip(session: AsyncSession) -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    attempt.pull_events()

    repository = SqlAlchemyAttemptRepository(session)
    await repository.save(attempt, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(attempt.id, tenant_id="tenant-123", user_id="user-123")
    assert retrieved is not None
    assert retrieved.id == attempt.id
    assert retrieved.status == AttemptStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_attempt_lookup_enforces_tenant_and_user_scope(
    session: AsyncSession,
) -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    attempt.pull_events()
    repository = SqlAlchemyAttemptRepository(session)
    await repository.save(attempt, tenant_id="tenant-123")

    assert await repository.get_by_id(attempt.id, tenant_id="tenant-999", user_id="user-123") is None
    assert await repository.get_by_id(attempt.id, tenant_id="tenant-123", user_id="user-999") is None


@pytest.mark.asyncio
async def test_active_attempt_lookup_and_submitted_history(
    session: AsyncSession,
) -> None:
    active = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    active.pull_events()
    repository = SqlAlchemyAttemptRepository(session)
    await repository.save(active, tenant_id="tenant-123")

    found = await repository.get_active_for_user("assessment-123", "user-123", "tenant-123")
    assert found is not None
    assert found.id == active.id

    active.submit()
    active.pull_events()
    await repository.update(active, tenant_id="tenant-123")

    assert await repository.get_active_for_user("assessment-123", "user-123", "tenant-123") is None
    attempts = await repository.list_by_user("user-123", "tenant-123")
    assert len(attempts) == 1
    assert attempts[0].status == AttemptStatus.SUBMITTED
