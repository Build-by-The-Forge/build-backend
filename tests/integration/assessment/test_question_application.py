import pytest
from app.application.assessment.question_service import QuestionService
from app.domain.assessment.question import Question
from app.domain.assessment.value_objects import (
    QuestionStatus,
)
from app.domain.catalogue.course import Course
from app.domain.catalogue.learning_outcome import LearningOutcome
from app.domain.catalogue.topic import Topic
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseTitle,
    DepartmentId,
    LearningOutcomeDescription,
    LearningOutcomeSequence,
    TopicDescription,
    TopicSequence,
    TopicSlug,
    TopicTitle,
)
from app.events.event_bus import EventBus


class InMemoryCourseRepository:
    def __init__(self, items: list[Course] | None = None):
        self.items = {course.id.value: course for course in (items or [])}

    @staticmethod
    def _matches_tenant(value: str, tenant_id: str | None) -> bool:
        return tenant_id is None or tenant_id in value

    async def get_by_topic_id(self, topic_id: str, tenant_id: str | None = None) -> Course | None:
        for course in self.items.values():
            if any(topic.id.value == topic_id for topic in course.topics):
                if self._matches_tenant(course.id.value, tenant_id):
                    return course
        return None

    async def get_by_learning_outcome_id(self, learning_outcome_id: str, tenant_id: str | None = None) -> Course | None:
        for course in self.items.values():
            for topic in course.topics:
                if any(item.id.value == learning_outcome_id for item in topic.learning_outcomes):
                    if self._matches_tenant(course.id.value, tenant_id):
                        return course
        return None


class InMemoryQuestionRepository:
    def __init__(self, items: list[Question] | None = None):
        self.items = {question.id.value: question for question in (items or [])}

    async def save(self, question: Question, tenant_id: str | None = None) -> Question:
        self.items[question.id.value] = question
        return question

    async def get_by_id(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        return self.items.get(question_id)

    async def list_by_topic(self, topic_id: str, tenant_id: str | None = None) -> list[Question]:
        return [question for question in self.items.values() if question.topic_id == topic_id]

    async def list_by_learning_outcome(self, learning_outcome_id: str, tenant_id: str | None = None) -> list[Question]:
        return [question for question in self.items.values() if question.learning_outcome_id == learning_outcome_id]

    async def list_all(self, tenant_id: str | None = None) -> list[Question]:
        return list(self.items.values())

    async def update(self, question: Question, tenant_id: str | None = None) -> Question:
        self.items[question.id.value] = question
        return question


@pytest.fixture
def course_repo():
    course = Course.create(
        department_id=DepartmentId("dept-1"),
        code=CourseCode("CS101"),
        title=CourseTitle("Intro to CS"),
        slug=CourseSlug("intro-to-cs"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
        course_id=CourseId("course-tenant-1"),
    )
    topic = Topic.create(
        course_id=course.id,
        title=TopicTitle("Algorithms"),
        slug=TopicSlug("algorithms"),
        description=TopicDescription("Algorithms topic"),
        sequence=TopicSequence(1),
        topic_id=CourseId("topic-tenant-1"),
    )
    outcome = LearningOutcome.create(
        topic_id=topic.id,
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Explain sorting"),
        learning_outcome_id=CourseId("outcome-tenant-1"),
    )
    topic.add_learning_outcome(outcome)
    course.add_topic(topic)
    return InMemoryCourseRepository([course])


@pytest.fixture
def question_service(course_repo):
    return QuestionService(
        repository=InMemoryQuestionRepository(),
        catalogue_repository=course_repo,
        event_bus=EventBus(),
    )


@pytest.mark.asyncio
async def test_create_question_success(question_service):
    question = await question_service.create_question(
        topic_id="topic-tenant-1",
        learning_outcome_id="outcome-tenant-1",
        question_type="mcq",
        prompt="Which sort is stable?",
        explanation="Merge sort is stable.",
        difficulty="easy",
        marks=2,
        options=[
            {"text": "Bubble sort", "display_order": 1, "is_correct": False},
            {"text": "Merge sort", "display_order": 2, "is_correct": True},
            {"text": "Hash sort", "display_order": 3, "is_correct": False},
        ],
        tenant_id="tenant-1",
    )

    assert question is not None
    assert question.prompt.value == "Which sort is stable?"
    assert question.status == QuestionStatus.DRAFT
    assert len(question.options) == 3
    assert question.options[1].is_correct is True


@pytest.mark.asyncio
async def test_create_question_rejects_learning_outcome_for_different_topic(
    question_service,
):
    other_course = Course.create(
        department_id=DepartmentId("dept-2"),
        code=CourseCode("CS201"),
        title=CourseTitle("Advanced Algorithms"),
        slug=CourseSlug("advanced-algorithms"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(200),
        semester=CourseSemester(2),
        course_id=CourseId("course-tenant-2"),
    )
    other_topic = Topic.create(
        course_id=other_course.id,
        title=TopicTitle("Graphs"),
        slug=TopicSlug("graphs"),
        description=TopicDescription("Graphs topic"),
        sequence=TopicSequence(1),
        topic_id=CourseId("topic-tenant-2"),
    )
    other_outcome = LearningOutcome.create(
        topic_id=other_topic.id,
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Describe DFS"),
        learning_outcome_id=CourseId("outcome-tenant-2"),
    )
    other_topic.add_learning_outcome(other_outcome)
    other_course.add_topic(other_topic)
    question_service.catalogue_repository.items[other_course.id.value] = other_course

    question = await question_service.create_question(
        topic_id="topic-tenant-1",
        learning_outcome_id="outcome-tenant-2",
        question_type="mcq",
        prompt="Wrong outcome",
        explanation="This should fail.",
        difficulty="easy",
        marks=1,
        options=[
            {"text": "One", "display_order": 1, "is_correct": False},
            {"text": "Two", "display_order": 2, "is_correct": True},
        ],
        tenant_id="tenant-1",
    )

    assert question is None


@pytest.mark.asyncio
async def test_update_question_success(question_service):
    created = await question_service.create_question(
        topic_id="topic-tenant-1",
        learning_outcome_id="outcome-tenant-1",
        question_type="mcq",
        prompt="Original prompt",
        explanation="Original explanation.",
        difficulty="easy",
        marks=1,
        options=[
            {"text": "Alpha", "display_order": 1, "is_correct": False},
            {"text": "Bravo", "display_order": 2, "is_correct": True},
        ],
        tenant_id="tenant-1",
    )

    updated = await question_service.update_question(
        question_id=created.id.value,
        prompt="Updated prompt",
        tenant_id="tenant-1",
    )

    assert updated is not None
    assert updated.prompt.value == "Updated prompt"


@pytest.mark.asyncio
async def test_publish_question_success(question_service):
    created = await question_service.create_question(
        topic_id="topic-tenant-1",
        learning_outcome_id="outcome-tenant-1",
        question_type="mcq",
        prompt="Publish me",
        explanation="Should become published.",
        difficulty="medium",
        marks=3,
        options=[
            {"text": "A", "display_order": 1, "is_correct": False},
            {"text": "B", "display_order": 2, "is_correct": True},
        ],
        tenant_id="tenant-1",
    )

    published = await question_service.publish_question(
        question_id=created.id.value,
        tenant_id="tenant-1",
    )

    assert published is not None
    assert published.status == QuestionStatus.PUBLISHED
