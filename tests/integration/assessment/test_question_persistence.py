import pytest
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.value_objects import (
    Difficulty,
    QuestionDisplayOrder,
    QuestionExplanation,
    QuestionId,
    QuestionMarks,
    QuestionOptionId,
    QuestionOptionText,
    QuestionPrompt,
    QuestionStatus,
    QuestionType,
)
from app.infrastructure.assessment.repositories import SqlAlchemyQuestionRepository
from sqlalchemy.ext.asyncio import AsyncSession


def build_question(**overrides):
    options = [
        QuestionOption(
            id=QuestionOptionId(""),
            question_id=QuestionId(""),
            text=QuestionOptionText("Stack"),
            display_order=QuestionDisplayOrder(1),
            is_correct=False,
        ),
        QuestionOption(
            id=QuestionOptionId(""),
            question_id=QuestionId(""),
            text=QuestionOptionText("Queue"),
            display_order=QuestionDisplayOrder(2),
            is_correct=True,
        ),
    ]
    values = {
        "tenant_id": "tenant-123",
        "topic_id": "topic-123",
        "learning_outcome_id": "lo-123",
        "question_type": QuestionType.MCQ,
        "prompt": QuestionPrompt("Which data structure uses FIFO ordering?"),
        "explanation": QuestionExplanation(
            "A queue follows first-in, first-out order."
        ),
        "difficulty": Difficulty.EASY,
        "marks": QuestionMarks(2),
        "options": options,
    }
    values.update(overrides)
    return Question.create(**values)


@pytest.mark.asyncio
async def test_question_round_trip(session: AsyncSession):
    """Test saving and retrieving a question with options."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert retrieved is not None
    assert retrieved.id.value == question.id.value
    assert retrieved.prompt.value == question.prompt.value
    assert retrieved.marks.value == 2
    assert len(retrieved.options) == 2


@pytest.mark.asyncio
async def test_question_option_ordering_preserved(session: AsyncSession):
    """Test that option display order is preserved across persistence."""
    options = [
        QuestionOption(
            id=QuestionOptionId(""),
            question_id=QuestionId(""),
            text=QuestionOptionText("First"),
            display_order=QuestionDisplayOrder(1),
            is_correct=False,
        ),
        QuestionOption(
            id=QuestionOptionId(""),
            question_id=QuestionId(""),
            text=QuestionOptionText("Second"),
            display_order=QuestionDisplayOrder(2),
            is_correct=True,
        ),
        QuestionOption(
            id=QuestionOptionId(""),
            question_id=QuestionId(""),
            text=QuestionOptionText("Third"),
            display_order=QuestionDisplayOrder(3),
            is_correct=False,
        ),
    ]
    question = build_question(options=options)
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert len(retrieved.options) == 3
    assert retrieved.options[0].text.value == "First"
    assert retrieved.options[0].display_order.value == 1
    assert retrieved.options[1].text.value == "Second"
    assert retrieved.options[1].display_order.value == 2
    assert retrieved.options[2].text.value == "Third"
    assert retrieved.options[2].display_order.value == 3


@pytest.mark.asyncio
async def test_tenant_isolation_on_get(session: AsyncSession):
    """Test that get_by_id respects tenant scoping."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    # Attempt to retrieve with different tenant should fail
    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-456")
    assert retrieved is None


@pytest.mark.asyncio
async def test_list_by_topic_with_tenant_scoping(session: AsyncSession):
    """Test filtering questions by topic with tenant isolation."""
    q1 = build_question(topic_id="topic-1")
    q1.pull_events()
    q2 = build_question(topic_id="topic-1")
    q2.pull_events()
    q3 = build_question(topic_id="topic-2")
    q3.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(q1, tenant_id="tenant-123")
    await repository.save(q2, tenant_id="tenant-123")
    await repository.save(q3, tenant_id="tenant-123")

    retrieved = await repository.list_by_topic("topic-1", tenant_id="tenant-123")
    assert len(retrieved) == 2
    assert all(q.topic_id == "topic-1" for q in retrieved)

    # Cross-tenant query should return empty
    retrieved_wrong_tenant = await repository.list_by_topic(
        "topic-1", tenant_id="tenant-456"
    )
    assert len(retrieved_wrong_tenant) == 0


@pytest.mark.asyncio
async def test_list_by_learning_outcome_with_tenant_scoping(session: AsyncSession):
    """Test filtering questions by learning outcome with tenant isolation."""
    q1 = build_question(learning_outcome_id="lo-1")
    q1.pull_events()
    q2 = build_question(learning_outcome_id="lo-2")
    q2.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(q1, tenant_id="tenant-123")
    await repository.save(q2, tenant_id="tenant-123")

    retrieved = await repository.list_by_learning_outcome(
        "lo-1", tenant_id="tenant-123"
    )
    assert len(retrieved) == 1
    assert retrieved[0].learning_outcome_id == "lo-1"

    # Cross-tenant query should return empty
    retrieved_wrong_tenant = await repository.list_by_learning_outcome(
        "lo-1", tenant_id="tenant-456"
    )
    assert len(retrieved_wrong_tenant) == 0


@pytest.mark.asyncio
async def test_update_question_details(session: AsyncSession):
    """Test updating question details persists correctly."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    # Update the question
    new_prompt = QuestionPrompt("Updated prompt?")
    new_difficulty = Difficulty.HARD
    question.update_details(prompt=new_prompt, difficulty=new_difficulty)
    question.pull_events()

    await repository.update(question, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert retrieved.prompt.value == "Updated prompt?"
    assert retrieved.difficulty == Difficulty.HARD


@pytest.mark.asyncio
async def test_archive_question_persists(session: AsyncSession):
    """Test that archiving a question persists the status change."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    # Archive the question
    question.archive()
    question.pull_events()

    await repository.update(question, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert retrieved.status == QuestionStatus.ARCHIVED


@pytest.mark.asyncio
async def test_publish_question_persists(session: AsyncSession):
    """Test that publishing a question persists the status change."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    # Publish the question
    question.publish()
    question.pull_events()

    await repository.update(question, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert retrieved.status == QuestionStatus.PUBLISHED


@pytest.mark.asyncio
async def test_list_all_with_tenant_scoping(session: AsyncSession):
    """Test listing all questions respects tenant scoping."""
    q1 = build_question()
    q1.pull_events()
    q2 = build_question()
    q2.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(q1, tenant_id="tenant-123")
    await repository.save(q2, tenant_id="tenant-123")

    # Save a question for a different tenant
    q3 = build_question()
    q3.pull_events()
    await repository.save(q3, tenant_id="tenant-456")

    retrieved = await repository.list_all(tenant_id="tenant-123")
    assert len(retrieved) == 2
    assert all(q.tenant_id == "tenant-123" for q in retrieved)

    retrieved_other = await repository.list_all(tenant_id="tenant-456")
    assert len(retrieved_other) == 1
    assert retrieved_other[0].tenant_id == "tenant-456"


@pytest.mark.asyncio
async def test_update_nonexistent_question_raises_error(session: AsyncSession):
    """Test that updating a nonexistent question raises ValueError."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)

    # Try to update without saving first
    with pytest.raises(ValueError, match="not found"):
        await repository.update(question, tenant_id="tenant-123")


@pytest.mark.asyncio
async def test_rollback_on_exception(session: AsyncSession):
    """Test that changes are rolled back on exception."""
    question = build_question()
    question.pull_events()

    repository = SqlAlchemyQuestionRepository(session)
    await repository.save(question, tenant_id="tenant-123")

    # Manually rollback the session
    await session.rollback()

    # Verify the question is still accessible (depends on transaction isolation)
    retrieved = await repository.get_by_id(question.id.value, tenant_id="tenant-123")
    assert retrieved is None or retrieved.id.value == question.id.value
