import pytest

from app.domain.assessment.errors import QuestionAlreadyArchivedError
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.value_objects import (
    Difficulty,
    QuestionExplanation,
    QuestionMarks,
    QuestionPrompt,
    QuestionType,
    QuestionOptionText,
    QuestionDisplayOrder,
    QuestionId,
    QuestionOptionId,
)


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
        "explanation": QuestionExplanation("A queue follows first-in, first-out order."),
        "difficulty": Difficulty.EASY,
        "marks": QuestionMarks(2),
        "options": options,
    }
    values.update(overrides)
    return Question.create(**values)


def test_question_create_valid_mcq():
    question = build_question()

    assert question.status.value == "draft"
    assert question.question_type == QuestionType.MCQ
    assert question.prompt.value == "Which data structure uses FIFO ordering?"
    assert len(question.options) == 2
    events = question.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "question.created"


def test_question_requires_at_least_two_options():
    with pytest.raises(ValueError, match="at least 2 options"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("Which is correct?"),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(2),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("Only option"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=True,
                )
            ],
        )


def test_question_requires_exactly_one_correct_option():
    with pytest.raises(ValueError, match="exactly one correct option"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("Which is correct?"),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(2),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("A"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=True,
                ),
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("B"),
                    display_order=QuestionDisplayOrder(2),
                    is_correct=True,
                ),
            ],
        )


def test_question_rejects_duplicate_display_order():
    with pytest.raises(ValueError, match="display order"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("Which is correct?"),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(2),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("A"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=False,
                ),
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("B"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=True,
                ),
            ],
        )


def test_question_rejects_empty_prompt():
    with pytest.raises(ValueError, match="non-empty prompt"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("   "),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(2),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("A"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=False,
                ),
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("B"),
                    display_order=QuestionDisplayOrder(2),
                    is_correct=True,
                ),
            ],
        )


def test_question_rejects_empty_option_text():
    with pytest.raises(ValueError, match="non-empty option text"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("What is correct?"),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(2),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText(""),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=False,
                ),
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("B"),
                    display_order=QuestionDisplayOrder(2),
                    is_correct=True,
                ),
            ],
        )


def test_question_rejects_non_positive_marks():
    with pytest.raises(ValueError, match="positive"):
        Question.create(
            tenant_id="tenant-123",
            topic_id="topic-123",
            question_type=QuestionType.MCQ,
            prompt=QuestionPrompt("What is correct?"),
            explanation=QuestionExplanation("Explain."),
            difficulty=Difficulty.EASY,
            marks=QuestionMarks(0),
            options=[
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("A"),
                    display_order=QuestionDisplayOrder(1),
                    is_correct=False,
                ),
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText("B"),
                    display_order=QuestionDisplayOrder(2),
                    is_correct=True,
                ),
            ],
        )


def test_question_can_publish_and_archive():
    question = build_question()
    question.pull_events()

    question.publish()
    publish_events = question.pull_events()
    assert question.status.value == "published"
    assert publish_events[0].event_type == "question.published"

    question.archive()
    archive_events = question.pull_events()
    assert question.status.value == "archived"
    assert archive_events[0].event_type == "question.archived"


def test_archived_question_cannot_be_modified():
    question = build_question()
    question.archive()
    question.pull_events()

    with pytest.raises(QuestionAlreadyArchivedError):
        question.update_details(prompt=QuestionPrompt("Updated prompt"))
