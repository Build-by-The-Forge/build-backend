import pytest
from app.domain.tenant.errors import FacultyAlreadyArchivedError
from app.domain.tenant.faculty import Faculty
from app.domain.tenant.value_objects import (
    FacultyName,
    FacultySlug,
    FacultyStatus,
    TenantId,
)


def test_faculty_must_belong_to_tenant() -> None:
    tenant_id = TenantId("")
    faculty = Faculty.create(
        tenant_id=tenant_id,
        name=FacultyName("School of Computing"),
        slug=FacultySlug("soc"),
    )

    assert faculty.tenant_id.value == tenant_id.value
    assert faculty.is_active is True


def test_faculty_slug_validates() -> None:
    with pytest.raises(ValueError):
        FacultySlug("ab")

    with pytest.raises(ValueError):
        FacultySlug("Invalid Slug")


def test_faculty_create_emits_event() -> None:
    faculty = Faculty.create(
        tenant_id=TenantId(""),
        name=FacultyName("School of Computing"),
        slug=FacultySlug("soc"),
    )

    events = faculty.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "faculty.created"
    assert events[0].payload["slug"] == "soc"


def test_faculty_rename_and_archive() -> None:
    faculty = Faculty.create(
        tenant_id=TenantId(""),
        name=FacultyName("School of Computing"),
        slug=FacultySlug("soc"),
    )
    faculty.pull_events()

    faculty.rename(FacultyName("School of Computing and Informatics"))
    assert "Informatics" in faculty.name.value

    faculty.archive()
    assert faculty.status == FacultyStatus.ARCHIVED

    with pytest.raises(FacultyAlreadyArchivedError):
        faculty.archive()
