import pytest
from app.application.assessment.assessment_service import AssessmentService
from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.domain.assessment.errors import AssessmentAlreadyArchivedError
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.value_objects import (
    QuestionDisplayOrder,
    QuestionId,
    QuestionMarks,
    QuestionOptionId,
    QuestionOptionText,
    QuestionPrompt,
    QuestionType,
)
from app.events.event_bus import EventBus


class InMemoryAssessmentRepository:
    def __init__(self) -> None:
        self.items: dict[str, Assessment] = {}

    async def save(self, assessment: Assessment, tenant_id: str | None = None) -> Assessment:
        self.items[assessment.id] = assessment
        return assessment

    async def get_by_id(self, assessment_id: str, tenant_id: str | None = None) -> Assessment | None:
        assessment = self.items.get(assessment_id)
        if assessment is not None and tenant_id is not None and assessment.tenant_id != tenant_id:
            return None
        return assessment

    async def list_by_course(self, course_id: str, tenant_id: str | None = None) -> list[Assessment]:
        return [
            assessment
            for assessment in self.items.values()
            if assessment.course_id == course_id and (tenant_id is None or assessment.tenant_id == tenant_id)
        ]

    async def list_all(self, tenant_id: str | None = None) -> list[Assessment]:
        return [assessment for assessment in self.items.values() if tenant_id is None or assessment.tenant_id == tenant_id]

    async def update(self, assessment: Assessment, tenant_id: str | None = None) -> Assessment:
        existing = await self.get_by_id(assessment.id, tenant_id=tenant_id)
        if existing is None:
            raise ValueError("assessment not found")
        self.items[assessment.id] = assessment
        return assessment


class InMemoryQuestionRepository:
    def __init__(self, question: Question) -> None:
        self.question = question

    async def get_by_id(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        if question_id != self.question.id.value:
            return None
        if tenant_id is not None and tenant_id != self.question.tenant_id:
            return None
        return self.question


class InMemoryCourseRepository:
    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> object | None:
        if course_id == "course-123" and tenant_id == "tenant-123":
            return object()
        return None


def build_question() -> Question:
    return Question.create(
        tenant_id="tenant-123",
        topic_id="topic-123",
        question_type=QuestionType.MCQ,
        prompt=QuestionPrompt("Which data structure is FIFO?"),
        marks=QuestionMarks(2),
        options=[
            QuestionOption(
                id=QuestionOptionId("option-1"),
                question_id=QuestionId("question-123"),
                text=QuestionOptionText("Stack"),
                display_order=QuestionDisplayOrder(1),
            ),
            QuestionOption(
                id=QuestionOptionId("option-2"),
                question_id=QuestionId("question-123"),
                text=QuestionOptionText("Queue"),
                display_order=QuestionDisplayOrder(2),
                is_correct=True,
            ),
        ],
        question_id=QuestionId("question-123"),
    )


@pytest.fixture
def assessment_service() -> AssessmentService:
    return AssessmentService(
        repository=InMemoryAssessmentRepository(),
        question_repository=InMemoryQuestionRepository(build_question()),
        catalogue_repository=InMemoryCourseRepository(),
        event_bus=EventBus(),
    )


@pytest.mark.asyncio
async def test_create_get_and_list_assessments(
    assessment_service: AssessmentService,
) -> None:
    created = await assessment_service.create_assessment(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )

    retrieved = await assessment_service.get_assessment(created.id, "tenant-123")
    listed = await assessment_service.list_assessments("tenant-123", "course-123")

    assert retrieved is created
    assert listed == [created]
    assert await assessment_service.get_assessment(created.id, "tenant-999") is None


@pytest.mark.asyncio
async def test_update_and_publish_assessment(
    assessment_service: AssessmentService,
) -> None:
    assessment = await assessment_service.create_assessment("tenant-123", "course-123", "Midterm", "Original instructions", 60)

    updated = await assessment_service.update_assessment(
        assessment.id,
        "tenant-123",
        title="Updated Midterm",
        duration_minutes=90,
    )
    await assessment_service.add_question(assessment.id, "question-123", "tenant-123")
    published = await assessment_service.publish_assessment(assessment.id, "tenant-123")

    assert updated is not None
    assert updated.title == "Updated Midterm"
    assert updated.duration_minutes == 90
    assert published is not None
    assert published.status == AssessmentStatus.PUBLISHED


@pytest.mark.asyncio
async def test_add_question_preserves_question_snapshot_and_rejects_duplicate(
    assessment_service: AssessmentService,
) -> None:
    assessment = await assessment_service.create_assessment("tenant-123", "course-123", "Midterm", "Answer all questions.", 60)

    added = await assessment_service.add_question(assessment.id, "question-123", "tenant-123")

    assert added is not None
    assert added.questions[0].prompt == "Which data structure is FIFO?"
    assert added.questions[0].marks == 2

    with pytest.raises(ValueError, match="already exists"):
        await assessment_service.add_question(assessment.id, "question-123", "tenant-123")


@pytest.mark.asyncio
async def test_create_requires_course_in_direct_repository_mode() -> None:
    service = AssessmentService(
        repository=InMemoryAssessmentRepository(),
        catalogue_repository=None,
    )

    with pytest.raises(ValueError, match="catalogue repository is required"):
        await service.create_assessment("tenant-123", "course-123", "Midterm", "Answer all questions.", 60)


@pytest.mark.asyncio
async def test_assessment_events_are_published_after_application_operations() -> None:
    events: list[str] = []
    event_bus = EventBus()
    for event_type in (
        "assessment.created",
        "assessment.updated",
        "assessment.published",
    ):
        event_bus.subscribe(event_type, lambda event: events.append(event.event_type))

    service = AssessmentService(
        repository=InMemoryAssessmentRepository(),
        question_repository=InMemoryQuestionRepository(build_question()),
        catalogue_repository=InMemoryCourseRepository(),
        event_bus=event_bus,
    )
    assessment = await service.create_assessment("tenant-123", "course-123", "Midterm", "Answer all questions.", 60)
    await service.add_question(assessment.id, "question-123", "tenant-123")
    await service.update_assessment(assessment.id, "tenant-123", title="Updated")
    await service.publish_assessment(assessment.id, "tenant-123")

    assert events == [
        "assessment.created",
        "assessment.updated",
        "assessment.published",
    ]


@pytest.mark.asyncio
async def test_archived_assessment_update_propagates_domain_error(
    assessment_service: AssessmentService,
) -> None:
    assessment = await assessment_service.create_assessment("tenant-123", "course-123", "Midterm", "Answer all questions.", 60)
    assessment.archive()

    with pytest.raises(AssessmentAlreadyArchivedError):
        await assessment_service.update_assessment(assessment.id, "tenant-123", title="Should fail")
