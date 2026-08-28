import pytest
from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.infrastructure.assessment.repositories import SqlAlchemyAssessmentRepository
from sqlalchemy.ext.asyncio import AsyncSession


def build_assessment(**overrides):
    values = {
        "tenant_id": "tenant-123",
        "course_id": "course-123",
        "title": "Midterm Test",
        "instructions": "Answer all questions.",
        "duration_minutes": 60,
        "passing_score": 50,
    }
    values.update(overrides)
    assessment = Assessment.create(**values)
    assessment.add_question("question-1", "Prompt A", ["A", "B"], 3)
    assessment.add_question("question-2", "Prompt B", ["C", "D"], 2)
    assessment.pull_events()
    return assessment


@pytest.mark.asyncio
async def test_assessment_round_trip(session: AsyncSession):
    assessment = build_assessment()

    repository = SqlAlchemyAssessmentRepository(session)
    await repository.save(assessment, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(assessment.id, tenant_id="tenant-123")
    assert retrieved is not None
    assert retrieved.id == assessment.id
    assert retrieved.title == "Midterm Test"
    assert retrieved.status == AssessmentStatus.DRAFT
    assert len(retrieved.questions) == 2
    assert retrieved.questions[0].question_id == "question-1"
    assert retrieved.questions[0].marks == 3


@pytest.mark.asyncio
async def test_assessment_list_by_course_with_tenant_scope(session: AsyncSession):
    assessment_1 = build_assessment(course_id="course-1")
    assessment_2 = build_assessment(course_id="course-1")
    assessment_3 = build_assessment(course_id="course-2")

    repository = SqlAlchemyAssessmentRepository(session)
    await repository.save(assessment_1, tenant_id="tenant-123")
    await repository.save(assessment_2, tenant_id="tenant-123")
    await repository.save(assessment_3, tenant_id="tenant-123")

    retrieved = await repository.list_by_course("course-1", tenant_id="tenant-123")
    assert len(retrieved) == 2
    assert {item.title for item in retrieved} == {"Midterm Test"}

    wrong_tenant = await repository.list_by_course("course-1", tenant_id="tenant-999")
    assert wrong_tenant == []


@pytest.mark.asyncio
async def test_assessment_update_persists_status_change(session: AsyncSession):
    assessment = build_assessment()

    repository = SqlAlchemyAssessmentRepository(session)
    await repository.save(assessment, tenant_id="tenant-123")

    assessment.publish()
    await repository.update(assessment, tenant_id="tenant-123")

    retrieved = await repository.get_by_id(assessment.id, tenant_id="tenant-123")
    assert retrieved is not None
    assert retrieved.status == AssessmentStatus.PUBLISHED


@pytest.mark.asyncio
async def test_question_snapshots_are_tenant_scoped_and_sequence_ordered(
    session: AsyncSession,
):
    assessment = build_assessment()
    repository = SqlAlchemyAssessmentRepository(session)
    await repository.save(assessment, tenant_id="tenant-123")

    snapshots = await repository.list_question_snapshots(
        assessment.id, tenant_id="tenant-123"
    )

    assert [item.question_id for item in snapshots] == ["question-1", "question-2"]
    assert snapshots[0].prompt == "Prompt A"
    assert snapshots[0].options == ["A", "B"]
    assert (
        await repository.list_question_snapshots(assessment.id, tenant_id="tenant-999")
        == []
    )
