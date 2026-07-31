from datetime import date

import pytest

from app.domain.tenant.errors import SemesterAlreadyArchivedError
from app.domain.tenant.semester import Semester
from app.domain.tenant.value_objects import (
    AcademicSessionId,
    SemesterName,
    SemesterNumber,
    SemesterStatus,
    TenantId,
)


def test_semester_belongs_to_session() -> None:
    sem = Semester.create(
        tenant_id=TenantId(""),
        academic_session_id=AcademicSessionId(""),
        number=SemesterNumber.FIRST,
        start_date=date(2025, 9, 1),
        end_date=date(2026, 1, 15),
        is_current=True,
    )

    assert sem.number == SemesterNumber.FIRST
    assert sem.name.value == "First Semester"
    assert sem.is_current is True


def test_semester_second_defaults_name() -> None:
    sem = Semester.create(
        tenant_id=TenantId(""),
        academic_session_id=AcademicSessionId(""),
        number=SemesterNumber.SECOND,
    )

    assert sem.name.value == "Second Semester"


def test_semester_create_emits_event() -> None:
    sem = Semester.create(
        tenant_id=TenantId(""),
        academic_session_id=AcademicSessionId(""),
        number=SemesterNumber.FIRST,
    )

    events = sem.pull_events()
    assert events[0].event_type == "semester.created"
    assert events[0].payload["number"] == 1


def test_semester_mark_current_and_archive() -> None:
    sem = Semester.create(
        tenant_id=TenantId(""),
        academic_session_id=AcademicSessionId(""),
        number=SemesterNumber.FIRST,
        start_date=date(2025, 9, 1),
        end_date=date(2026, 1, 15),
    )
    sem.pull_events()

    sem.mark_as_current()
    assert sem.is_current is True

    sem.archive()
    assert sem.status == SemesterStatus.ARCHIVED
    assert sem.is_current is False

    with pytest.raises(SemesterAlreadyArchivedError):
        sem.archive()
