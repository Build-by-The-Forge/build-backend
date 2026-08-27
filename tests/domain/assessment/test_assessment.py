import pytest

from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.domain.assessment.errors import AssessmentAlreadyArchivedError


def test_assessment_create_valid_draft():
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm Test",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )

    assert assessment.status == AssessmentStatus.DRAFT
    assert assessment.title == "Midterm Test"
    assert assessment.question_count == 0
    assert assessment.pass_mark == 50
    events = assessment.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "assessment.created"


def test_assessment_rejects_duplicate_question_ids():
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm Test",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )

    assessment.add_question("question-1", "Prompt A", ["A", "B"], 5)

    with pytest.raises(ValueError, match="already exists"):
        assessment.add_question("question-1", "Prompt A", ["A", "B"], 5)


def test_assessment_publish_and_close_transitions():
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm Test",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )

    assessment.publish()
    assert assessment.status == AssessmentStatus.PUBLISHED

    assessment.open()
    assert assessment.status == AssessmentStatus.OPEN

    assessment.close()
    assert assessment.status == AssessmentStatus.CLOSED


def test_assessment_archive_blocks_reopening():
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Midterm Test",
        instructions="Answer all questions.",
        duration_minutes=60,
        passing_score=50,
    )

    assessment.archive()
    assert assessment.status == AssessmentStatus.ARCHIVED

    with pytest.raises(AssessmentAlreadyArchivedError):
        assessment.publish()
