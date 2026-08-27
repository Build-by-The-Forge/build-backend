from __future__ import annotations

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
from app.infrastructure.db.models.assessment import (
    QuestionModel,
    QuestionOptionModel,
)


def question_option_to_model(
    option: QuestionOption,
    model: QuestionOptionModel | None = None,
) -> QuestionOptionModel:
    if model is None:
        model = QuestionOptionModel(id=option.id.value)

    if option.question_id is not None:
        model.question_id = option.question_id.value
    model.text = option.text.value
    model.display_order = int(option.display_order.value)
    model.is_correct = option.is_correct
    return model


def question_to_model(
    question: Question,
    model: QuestionModel | None = None,
) -> QuestionModel:
    if model is None:
        model = QuestionModel(id=question.id.value)

    model.tenant_id = question.tenant_id
    model.topic_id = question.topic_id
    model.learning_outcome_id = question.learning_outcome_id
    model.question_type = question.question_type.value
    model.prompt = question.prompt.value
    model.explanation = (
        question.explanation.value if question.explanation is not None else None
    )
    model.difficulty = question.difficulty.value
    model.marks = int(question.marks.value)
    model.status = question.status.value
    model.created_at = question.created_at
    model.updated_at = question.updated_at

    existing_options = {option.id: option for option in model.options or []}
    model.options = [
        question_option_to_model(
            option,
            model=existing_options.get(option.id.value),
        )
        for option in question.options
    ]
    return model


def question_option_model_to_domain(model: QuestionOptionModel) -> QuestionOption:
    return QuestionOption(
        id=QuestionOptionId(model.id),
        question_id=QuestionId(model.question_id),
        text=QuestionOptionText(model.text),
        display_order=QuestionDisplayOrder(model.display_order),
        is_correct=model.is_correct,
    )


def question_model_to_domain(model: QuestionModel) -> Question:
    return Question(
        id=QuestionId(model.id),
        tenant_id=model.tenant_id,
        topic_id=model.topic_id,
        learning_outcome_id=model.learning_outcome_id,
        question_type=QuestionType(model.question_type),
        prompt=QuestionPrompt(model.prompt),
        explanation=(
            QuestionExplanation(model.explanation)
            if model.explanation is not None
            else None
        ),
        difficulty=Difficulty(model.difficulty),
        marks=QuestionMarks(model.marks),
        status=QuestionStatus(model.status),
        options=[question_option_model_to_domain(opt) for opt in (model.options or [])],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
