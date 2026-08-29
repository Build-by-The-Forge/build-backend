from __future__ import annotations

import json
from datetime import datetime, timezone

from app.domain.assessment.assessment import (
    Assessment,
    AssessmentQuestion,
    AssessmentStatus,
)
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.result import AttemptResult, QuestionResult
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
    AssessmentAttemptModel,
    AssessmentAttemptResultModel,
    AssessmentModel,
    AssessmentQuestionModel,
    AttemptAnswerModel,
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


def assessment_question_to_model(
    question: AssessmentQuestion,
    *,
    assessment_id: str,
    sequence: int,
    model: AssessmentQuestionModel | None = None,
) -> AssessmentQuestionModel:
    if model is None:
        model = AssessmentQuestionModel(
            id=f"{assessment_id}-{sequence}-{question.question_id}"
        )

    model.assessment_id = assessment_id
    model.sequence = sequence
    model.question_id = question.question_id
    model.prompt = question.prompt
    model.options_json = json.dumps(question.options)
    model.correct_option_index = question.correct_option_index
    model.marks = question.marks
    model.is_active = True
    model.updated_at = datetime.now(timezone.utc)
    return model


def assessment_to_model(
    assessment: Assessment,
    model: AssessmentModel | None = None,
) -> AssessmentModel:
    if model is None:
        model = AssessmentModel(id=assessment.id)

    model.tenant_id = assessment.tenant_id
    model.course_id = assessment.course_id
    model.title = assessment.title
    model.instructions = assessment.instructions
    model.duration_minutes = assessment.duration_minutes
    model.passing_score = assessment.passing_score
    model.status = assessment.status.value
    model.created_at = assessment.created_at
    model.updated_at = assessment.updated_at

    existing_questions = {item.question_id: item for item in model.questions or []}
    model.questions = [
        assessment_question_to_model(
            question,
            assessment_id=model.id,
            sequence=index,
            model=existing_questions.get(question.question_id),
        )
        for index, question in enumerate(assessment.questions)
    ]
    return model


def assessment_question_model_to_domain(
    model: AssessmentQuestionModel,
) -> AssessmentQuestion:
    return AssessmentQuestion(
        question_id=model.question_id,
        prompt=model.prompt,
        options=json.loads(model.options_json),
        marks=model.marks,
        assessment_question_id=model.id,
        correct_option_index=model.correct_option_index,
    )


def assessment_model_to_domain(model: AssessmentModel) -> Assessment:
    assessment = Assessment(
        tenant_id=model.tenant_id,
        course_id=model.course_id,
        title=model.title,
        instructions=model.instructions,
        duration_minutes=model.duration_minutes,
        passing_score=model.passing_score,
        assessment_id=model.id,
        status=AssessmentStatus(model.status),
        questions=[
            assessment_question_model_to_domain(item)
            for item in (model.questions or [])
        ],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
    return assessment


def attempt_to_model(
    attempt: AssessmentAttempt,
    model: AssessmentAttemptModel | None = None,
) -> AssessmentAttemptModel:
    if model is None:
        model = AssessmentAttemptModel(id=attempt.id)

    model.tenant_id = attempt.tenant_id
    model.assessment_id = attempt.assessment_id
    model.user_id = attempt.user_id
    model.status = attempt.status.value
    model.started_at = attempt.started_at
    model.submitted_at = attempt.submitted_at
    model.created_at = attempt.created_at
    model.updated_at = attempt.updated_at
    return model


def attempt_model_to_domain(model: AssessmentAttemptModel) -> AssessmentAttempt:
    return AssessmentAttempt(
        tenant_id=model.tenant_id,
        assessment_id=model.assessment_id,
        user_id=model.user_id,
        status=AttemptStatus(model.status),
        attempt_id=model.id,
        started_at=model.started_at,
        submitted_at=model.submitted_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def attempt_answer_to_model(
    answer: AttemptAnswer,
    model: AttemptAnswerModel | None = None,
) -> AttemptAnswerModel:
    if model is None:
        model = AttemptAnswerModel(id=answer.id)
    model.tenant_id = answer.tenant_id
    model.attempt_id = answer.attempt_id
    model.assessment_question_id = answer.assessment_question_id
    model.selected_option_index = answer.selected_option_index
    model.created_at = answer.created_at
    model.updated_at = answer.updated_at
    return model


def attempt_answer_model_to_domain(model: AttemptAnswerModel) -> AttemptAnswer:
    return AttemptAnswer(
        tenant_id=model.tenant_id,
        attempt_id=model.attempt_id,
        assessment_question_id=model.assessment_question_id,
        selected_option_index=model.selected_option_index,
        answer_id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def attempt_result_to_model(
    result: AttemptResult,
    model: AssessmentAttemptResultModel | None = None,
) -> AssessmentAttemptResultModel:
    if model is None:
        model = AssessmentAttemptResultModel(id=result.id)
    model.tenant_id = result.tenant_id
    model.attempt_id = result.attempt_id
    model.assessment_id = result.assessment_id
    model.user_id = result.user_id
    model.total_score = result.total_score
    model.max_score = result.max_score
    model.percentage = result.percentage
    model.passed = result.passed
    model.breakdown_json = json.dumps(
        [
            {
                "assessment_question_id": item.assessment_question_id,
                "selected_option_index": item.selected_option_index,
                "correct_option_index": item.correct_option_index,
                "awarded_marks": item.awarded_marks,
                "max_marks": item.max_marks,
                "is_correct": item.is_correct,
            }
            for item in result.breakdown
        ]
    )
    model.graded_at = result.graded_at
    model.created_at = result.created_at
    model.updated_at = result.updated_at
    return model


def attempt_result_model_to_domain(
    model: AssessmentAttemptResultModel,
) -> AttemptResult:
    breakdown_data = json.loads(model.breakdown_json or "[]")
    breakdown = [
        QuestionResult(
            assessment_question_id=item["assessment_question_id"],
            selected_option_index=item.get("selected_option_index"),
            correct_option_index=item["correct_option_index"],
            awarded_marks=item["awarded_marks"],
            max_marks=item["max_marks"],
            is_correct=item["is_correct"],
        )
        for item in breakdown_data
    ]
    return AttemptResult(
        tenant_id=model.tenant_id,
        attempt_id=model.attempt_id,
        assessment_id=model.assessment_id,
        user_id=model.user_id,
        total_score=model.total_score,
        max_score=model.max_score,
        percentage=model.percentage,
        passed=model.passed,
        breakdown=breakdown,
        result_id=model.id,
        graded_at=model.graded_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
