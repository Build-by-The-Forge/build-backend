import pytest
from app.domain.tenant.errors import ProgrammeAlreadyArchivedError
from app.domain.tenant.programme import Programme
from app.domain.tenant.value_objects import (
    DepartmentId,
    FacultyId,
    ProgrammeCode,
    ProgrammeName,
    ProgrammeSlug,
    ProgrammeStatus,
    TenantId,
)


def test_programme_belongs_to_department() -> None:
    prog = Programme.create(
        tenant_id=TenantId(""),
        faculty_id=FacultyId(""),
        department_id=DepartmentId(""),
        name=ProgrammeName("BSc Computer Science"),
        slug=ProgrammeSlug("bsc-computer-science"),
        code=ProgrammeCode("BSC-CSC"),
        duration_years=4,
    )

    assert prog.duration_years == 4
    assert prog.code.value == "BSC-CSC"
    assert prog.is_active is True


def test_programme_duration_validates() -> None:
    with pytest.raises(ValueError):
        Programme.create(
            tenant_id=TenantId(""),
            faculty_id=FacultyId(""),
            department_id=DepartmentId(""),
            name=ProgrammeName("BSc Computer Science"),
            slug=ProgrammeSlug("bsc-computer-science"),
            code=ProgrammeCode("BSC-CSC"),
            duration_years=10,
        )


def test_programme_create_emits_event() -> None:
    prog = Programme.create(
        tenant_id=TenantId(""),
        faculty_id=FacultyId(""),
        department_id=DepartmentId(""),
        name=ProgrammeName("BSc Software Engineering"),
        slug=ProgrammeSlug("bsc-software-engineering"),
        code=ProgrammeCode("BSC-SEN"),
    )

    events = prog.pull_events()
    assert events[0].event_type == "programme.created"
    assert events[0].payload["code"] == "BSC-SEN"


def test_programme_rename_and_archive() -> None:
    prog = Programme.create(
        tenant_id=TenantId(""),
        faculty_id=FacultyId(""),
        department_id=DepartmentId(""),
        name=ProgrammeName("BSc Computer Science"),
        slug=ProgrammeSlug("bsc-computer-science"),
        code=ProgrammeCode("BSC-CSC"),
    )
    prog.pull_events()

    prog.rename(ProgrammeName("BSc Computer Science and Informatics"))
    assert "Informatics" in prog.name.value

    prog.archive()
    assert prog.status == ProgrammeStatus.ARCHIVED

    with pytest.raises(ProgrammeAlreadyArchivedError):
        prog.archive()
