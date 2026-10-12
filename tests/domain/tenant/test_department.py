import pytest

from app.domain.tenant.department import Department
from app.domain.tenant.errors import DepartmentAlreadyArchivedError
from app.domain.tenant.value_objects import (
    DepartmentCode,
    DepartmentName,
    DepartmentSlug,
    DepartmentStatus,
    FacultyId,
    TenantId,
)


def test_department_belongs_to_faculty_and_tenant() -> None:
    tenant_id = TenantId("")
    faculty_id = FacultyId("")

    dept = Department.create(
        tenant_id=tenant_id,
        faculty_id=faculty_id,
        name=DepartmentName("Computer Science"),
        slug=DepartmentSlug("computer-science"),
        code=DepartmentCode("CSC"),
    )

    assert dept.tenant_id.value == tenant_id.value
    assert dept.faculty_id.value == faculty_id.value
    assert dept.code and dept.code.value == "CSC"
    assert dept.is_active is True


def test_department_code_normalizes() -> None:
    code = DepartmentCode(" csc ")
    assert code.value == "CSC"

    with pytest.raises(ValueError):
        DepartmentCode("A")


def test_department_create_emits_event() -> None:
    dept = Department.create(
        tenant_id=TenantId(""),
        faculty_id=FacultyId(""),
        name=DepartmentName("Data Science"),
        slug=DepartmentSlug("data-science"),
    )

    events = dept.pull_events()
    assert events[0].event_type == "department.created"
    assert events[0].payload["slug"] == "data-science"


def test_department_change_code_and_archive() -> None:
    dept = Department.create(
        tenant_id=TenantId(""),
        faculty_id=FacultyId(""),
        name=DepartmentName("Software Engineering"),
        slug=DepartmentSlug("software-engineering"),
        code=DepartmentCode("SEN"),
    )
    dept.pull_events()

    dept.change_code(DepartmentCode("SWE"))
    assert dept.code and dept.code.value == "SWE"

    dept.archive()
    assert dept.status == DepartmentStatus.ARCHIVED

    with pytest.raises(DepartmentAlreadyArchivedError):
        dept.archive()
