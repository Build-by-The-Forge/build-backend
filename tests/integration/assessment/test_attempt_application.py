import pytest

from app.application.assessment.attempt_service import AttemptService
from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.events.event_bus import EventBus


class InMemoryAssessmentRepository:
    def __init__(self, assessment: Assessment) -> None:
        self.assessment = assessment

    async def get_by_id(self, assessment_id: str, tenant_id: str | None = None) -> Assessment | None:
        if assessment_id != self.assessment.id:
            return None
        if tenant_id is not None and tenant_id != self.assessment.tenant_id:
            return None
        return self.assessment


class InMemoryAttemptRepository:
    def __init__(self) -> None:
        self.items: dict[str, AssessmentAttempt] = {}

    async def save(self, attempt: AssessmentAttempt, tenant_id: str | None = None) -> AssessmentAttempt:
        self.items[attempt.id] = attempt
        return attempt

    async def get_by_id_for_update(
        self,
        attempt_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> AssessmentAttempt | None:
        return await self.get_by_id(attempt_id, tenant_id, user_id)

    async def get_by_id(
        self,
        attempt_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> AssessmentAttempt | None:
        attempt = self.items.get(attempt_id)
        if attempt is None:
            return None
        if tenant_id is not None and attempt.tenant_id != tenant_id:
            return None
        if user_id is not None and attempt.user_id != user_id:
            return None
        return attempt

    async def get_active_for_user(self, assessment_id: str, user_id: str, tenant_id: str) -> AssessmentAttempt | None:
        return next(
            (
                attempt
                for attempt in self.items.values()
                if attempt.assessment_id == assessment_id
                and attempt.user_id == user_id
                and attempt.tenant_id == tenant_id
                and attempt.status == AttemptStatus.IN_PROGRESS
            ),
            None,
        )

    async def list_by_user(self, user_id: str, tenant_id: str) -> list[AssessmentAttempt]:
        return [attempt for attempt in self.items.values() if attempt.user_id == user_id and attempt.tenant_id == tenant_id]

    async def update(self, attempt: AssessmentAttempt, tenant_id: str | None = None) -> AssessmentAttempt:
        existing = await self.get_by_id(attempt.id, tenant_id=tenant_id)
        if existing is None:
            raise ValueError("attempt not found")
        self.items[attempt.id] = attempt
        return attempt


def published_assessment() -> Assessment:
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )
    assessment.assessment_id = "assessment-123"
    assessment.add_question("question-123", "Prompt", ["A", "B"], 1)
    assessment.publish()
    assessment.pull_events()
    return assessment


@pytest.fixture
def attempt_setup() -> tuple[AttemptService, InMemoryAttemptRepository, list[str]]:
    attempt_repository = InMemoryAttemptRepository()
    events: list[str] = []
    event_bus = EventBus()
    event_bus.subscribe("attempt.started", lambda event: events.append(event.event_type))
    event_bus.subscribe("attempt.submitted", lambda event: events.append(event.event_type))
    service = AttemptService(
        repository=attempt_repository,
        assessment_repository=InMemoryAssessmentRepository(published_assessment()),
        event_bus=event_bus,
    )
    return service, attempt_repository, events


@pytest.mark.asyncio
async def test_start_attempt_resumes_active_attempt_and_publishes_event(
    attempt_setup,
) -> None:
    service, repository, events = attempt_setup

    first = await service.start_attempt("assessment-123", "tenant-123", "user-123")
    resumed = await service.start_attempt("assessment-123", "tenant-123", "user-123")

    assert resumed.id == first.id
    assert len(repository.items) == 1
    assert events == ["attempt.started"]


@pytest.mark.asyncio
async def test_start_attempt_requires_published_assessment(attempt_setup) -> None:
    service, _, _ = attempt_setup
    assessment_repository = service.assessment_repository
    assert assessment_repository is not None
    assessment_repository.assessment.status = AssessmentStatus.DRAFT

    with pytest.raises(ValueError, match="not available"):
        await service.start_attempt("assessment-123", "tenant-123", "user-123")


@pytest.mark.asyncio
async def test_get_and_list_attempts_are_scoped_to_owner_and_tenant(
    attempt_setup,
) -> None:
    service, _, _ = attempt_setup
    attempt = await service.start_attempt("assessment-123", "tenant-123", "user-123")

    assert await service.get_attempt(attempt.id, "tenant-123", "user-123") is not None
    assert await service.get_attempt(attempt.id, "tenant-123", "user-999") is None
    assert await service.get_attempt(attempt.id, "tenant-999", "user-123") is None
    assert await service.list_my_attempts("tenant-123", "user-123") == [attempt]
    assert await service.list_my_attempts("tenant-123", "user-999") == []


@pytest.mark.asyncio
async def test_submit_attempt_persists_state_and_allows_new_attempt(
    attempt_setup,
) -> None:
    service, repository, events = attempt_setup
    first = await service.start_attempt("assessment-123", "tenant-123", "user-123")

    submitted = await service.submit_attempt(first.id, "tenant-123", "user-123")
    second = await service.start_attempt("assessment-123", "tenant-123", "user-123")

    assert submitted is not None
    assert submitted.status == AttemptStatus.SUBMITTED
    assert submitted.submitted_at is not None
    assert second.id != first.id
    assert len(repository.items) == 2
    assert events == ["attempt.started", "attempt.submitted", "attempt.started"]


@pytest.mark.asyncio
async def test_submit_attempt_rejects_wrong_owner(attempt_setup) -> None:
    service, _, _ = attempt_setup
    attempt = await service.start_attempt("assessment-123", "tenant-123", "user-123")

    assert await service.submit_attempt(attempt.id, "tenant-123", "user-999") is None
