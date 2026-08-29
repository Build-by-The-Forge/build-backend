import pytest
from app.domain.catalogue.curriculum_version import CurriculumVersion
from app.domain.catalogue.errors import CurriculumVersionAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    CurriculumVersionName,
    CurriculumVersionStatus,
    ProgrammeId,
)
from app.domain.tenant.value_objects import AcademicSessionId


def test_curriculum_version_create_is_active() -> None:
    curriculum = CurriculumVersion.create(
        programme_id=ProgrammeId(""),
        name=CurriculumVersionName("BSc Data Science 2025"),
        version="2025-1",
        effective_session_id=AcademicSessionId(""),
    )

    assert curriculum.is_active is True
    assert curriculum.status == CurriculumVersionStatus.ACTIVE
    assert len(curriculum.pull_events()) == 1


def test_curriculum_version_archive_and_publish() -> None:
    curriculum = CurriculumVersion.create(
        programme_id=ProgrammeId(""),
        name=CurriculumVersionName("BSc Data Science 2025"),
        version="2025-1",
        effective_session_id=AcademicSessionId(""),
    )
    curriculum.pull_events()

    curriculum.archive()
    assert curriculum.status == CurriculumVersionStatus.ARCHIVED
    assert curriculum.pull_events()[0].event_type == "curriculum_version.archived"

    curriculum.publish()
    assert curriculum.status == CurriculumVersionStatus.ACTIVE
    assert curriculum.pull_events()[0].event_type == "curriculum_version.published"


def test_curriculum_version_archive_twice_raises() -> None:
    curriculum = CurriculumVersion.create(
        programme_id=ProgrammeId(""),
        name=CurriculumVersionName("BSc Data Science 2025"),
        version="2025-1",
        effective_session_id=AcademicSessionId(""),
    )
    curriculum.pull_events()

    curriculum.archive()

    with pytest.raises(CurriculumVersionAlreadyArchivedError):
        curriculum.archive()


def test_curriculum_version_add_course() -> None:
    curriculum = CurriculumVersion.create(
        programme_id=ProgrammeId(""),
        name=CurriculumVersionName("BSc Data Science 2025"),
        version="2025-1",
        effective_session_id=AcademicSessionId(""),
    )
    curriculum.pull_events()

    from app.domain.catalogue.value_objects import CourseId

    course_id = CourseId("")
    curriculum.add_course(course_id)

    assert course_id.value in [c.value for c in curriculum.course_ids]
    assert curriculum.pull_events()[0].event_type == "curriculum_version.course_added"
