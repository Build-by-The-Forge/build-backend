from app.domain.tenant.department import Department
from app.domain.tenant.faculty import Faculty
from app.domain.tenant.programme import Programme
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    DepartmentCode,
    DepartmentId,
    DepartmentName,
    DepartmentSlug,
    DepartmentStatus,
    FacultyId,
    FacultyName,
    FacultySlug,
    FacultyStatus,
    ProgrammeCode,
    ProgrammeId,
    ProgrammeName,
    ProgrammeSlug,
    ProgrammeStatus,
    TenantId,
    TenantName,
    TenantSlug,
    TenantStatus,
)

__all__ = [
    "Tenant",
    "Faculty",
    "Department",
    "Programme",
    "TenantId",
    "TenantName",
    "TenantSlug",
    "TenantStatus",
    "FacultyId",
    "FacultyName",
    "FacultySlug",
    "FacultyStatus",
    "DepartmentId",
    "DepartmentName",
    "DepartmentSlug",
    "DepartmentCode",
    "DepartmentStatus",
    "ProgrammeId",
    "ProgrammeName",
    "ProgrammeSlug",
    "ProgrammeCode",
    "ProgrammeStatus",
]
