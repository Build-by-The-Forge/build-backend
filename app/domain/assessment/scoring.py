from __future__ import annotations

from app.domain.assessment.assessment import Assessment, AssessmentQuestion
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.result import AttemptResult, QuestionResult


class AssessmentScorer:
    """Pure domain service for deterministic assessment scoring."""

    @staticmethod
    def score(
        *,
        attempt: AssessmentAttempt,
        assessment: Assessment,
        questions: list[AssessmentQuestion],
        answers: list[AttemptAnswer],
    ) -> AttemptResult:
        answers_by_question_id = {ans.assessment_question_id: ans for ans in answers}

        breakdown: list[QuestionResult] = []
        total_score = 0
        max_score = 0

        for question in questions:
            question_id = question.assessment_question_id or question.question_id
            max_score += question.marks
            correct_idx = (
                question.correct_option_index
                if question.correct_option_index is not None
                else 0
            )

            answer = answers_by_question_id.get(question_id)
            selected_idx = answer.selected_option_index if answer is not None else None

            is_correct = selected_idx is not None and selected_idx == correct_idx
            awarded_marks = question.marks if is_correct else 0
            total_score += awarded_marks

            breakdown.append(
                QuestionResult(
                    assessment_question_id=question_id,
                    selected_option_index=selected_idx,
                    correct_option_index=correct_idx,
                    awarded_marks=awarded_marks,
                    max_marks=question.marks,
                    is_correct=is_correct,
                )
            )

        percentage = (
            round((total_score / max_score * 100.0), 2) if max_score > 0 else 0.0
        )
        passed = total_score >= assessment.passing_score

        return AttemptResult.create(
            tenant_id=attempt.tenant_id,
            attempt_id=attempt.id,
            assessment_id=attempt.assessment_id,
            user_id=attempt.user_id,
            total_score=total_score,
            max_score=max_score,
            percentage=percentage,
            passed=passed,
            breakdown=breakdown,
        )
