from app.domain.assessment.assessment import Assessment, AssessmentQuestion
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.scoring import AssessmentScorer


def test_scorer_perfect_score() -> None:
    assessment = Assessment.create(
        tenant_id="tenant-1",
        course_id="course-1",
        title="Midterm Exam",
        instructions="Complete all questions",
        duration_minutes=60,
        passing_score=50,
    )
    q1 = AssessmentQuestion(
        question_id="q-1",
        assessment_question_id="aq-1",
        prompt="What is 2+2?",
        options=["3", "4", "5"],
        marks=2,
        correct_option_index=1,
    )
    q2 = AssessmentQuestion(
        question_id="q-2",
        assessment_question_id="aq-2",
        prompt="What is the capital of France?",
        options=["London", "Paris", "Berlin"],
        marks=3,
        correct_option_index=1,
    )
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-1",
        assessment_id=assessment.id,
        user_id="user-1",
        duration_minutes=30,
    )
    attempt.submit()

    answers = [
        AttemptAnswer.create(
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            assessment_question_id="aq-1",
            selected_option_index=1,
        ),
        AttemptAnswer.create(
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            assessment_question_id="aq-2",
            selected_option_index=1,
        ),
    ]

    result = AssessmentScorer.score(
        attempt=attempt,
        assessment=assessment,
        questions=[q1, q2],
        answers=answers,
    )

    assert result.total_score == 5
    assert result.max_score == 5
    assert result.percentage == 100.0
    assert result.passed is False  # 5 < passing_score of 50
    assert len(result.breakdown) == 2
    assert result.breakdown[0].is_correct is True
    assert result.breakdown[0].awarded_marks == 2
    assert result.breakdown[1].is_correct is True
    assert result.breakdown[1].awarded_marks == 3


def test_scorer_all_incorrect_and_passing_threshold() -> None:
    assessment = Assessment.create(
        tenant_id="tenant-1",
        course_id="course-1",
        title="Quiz",
        instructions="Instructions",
        duration_minutes=30,
        passing_score=3,
    )
    q1 = AssessmentQuestion(
        question_id="q-1",
        assessment_question_id="aq-1",
        prompt="Q1",
        options=["A", "B"],
        marks=3,
        correct_option_index=0,
    )
    q2 = AssessmentQuestion(
        question_id="q-2",
        assessment_question_id="aq-2",
        prompt="Q2",
        options=["A", "B"],
        marks=3,
        correct_option_index=1,
    )
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-1",
        assessment_id=assessment.id,
        user_id="user-1",
        duration_minutes=30,
    )

    # All answers wrong
    answers = [
        AttemptAnswer.create(
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            assessment_question_id="aq-1",
            selected_option_index=1,  # wrong
        ),
        AttemptAnswer.create(
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            assessment_question_id="aq-2",
            selected_option_index=0,  # wrong
        ),
    ]

    result = AssessmentScorer.score(
        attempt=attempt,
        assessment=assessment,
        questions=[q1, q2],
        answers=answers,
    )

    assert result.total_score == 0
    assert result.max_score == 6
    assert result.percentage == 0.0
    assert result.passed is False
    assert result.breakdown[0].is_correct is False
    assert result.breakdown[0].awarded_marks == 0
    assert result.breakdown[1].is_correct is False
    assert result.breakdown[1].awarded_marks == 0


def test_scorer_unanswered_questions_and_exact_pass() -> None:
    assessment = Assessment.create(
        tenant_id="tenant-1",
        course_id="course-1",
        title="Quiz",
        instructions="Instructions",
        duration_minutes=30,
        passing_score=4,
    )
    q1 = AssessmentQuestion(
        question_id="q-1",
        assessment_question_id="aq-1",
        prompt="Q1",
        options=["A", "B"],
        marks=4,
        correct_option_index=0,
    )
    q2 = AssessmentQuestion(
        question_id="q-2",
        assessment_question_id="aq-2",
        prompt="Q2",
        options=["A", "B"],
        marks=6,
        correct_option_index=1,
    )
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-1",
        assessment_id=assessment.id,
        user_id="user-1",
        duration_minutes=30,
    )

    # Only q1 is answered correctly, q2 is completely unanswered
    answers = [
        AttemptAnswer.create(
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            assessment_question_id="aq-1",
            selected_option_index=0,  # correct (4 marks)
        ),
    ]

    result = AssessmentScorer.score(
        attempt=attempt,
        assessment=assessment,
        questions=[q1, q2],
        answers=answers,
    )

    assert result.total_score == 4
    assert result.max_score == 10
    assert result.percentage == 40.0
    assert result.passed is True  # total_score 4 >= passing_score 4

    assert result.breakdown[0].is_correct is True
    assert result.breakdown[0].awarded_marks == 4
    assert result.breakdown[0].selected_option_index == 0

    assert result.breakdown[1].is_correct is False
    assert result.breakdown[1].awarded_marks == 0
    assert result.breakdown[1].selected_option_index is None
