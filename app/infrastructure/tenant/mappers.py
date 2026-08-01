from __future__ import annotations

from app.domain.tenant.academic_session import AcademicSession
from app.domain.tenant.department import Department
from app.domain.tenant.faculty import Faculty
from app.domain.tenant.level import Level
from app.domain.tenant.membership import Membership
from app.domain.tenant.programme import Programme
from app.domain.tenant.semester import Semester
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    AcademicSessionId,
    AcademicSessionName,
    AcademicSessionSlug,
    AcademicSessionStatus,
    DepartmentCode,
    DepartmentId,
    DepartmentName,
    DepartmentSlug,
    DepartmentStatus,
    FacultyId,
    FacultyName,
    FacultySlug,
    FacultyStatus,
    LevelCode,
    LevelId,
    LevelName,
    LevelStatus,
    MembershipId,
    MembershipRole,
    MembershipStatus,
    ProgrammeCode,
    ProgrammeId,
    ProgrammeName,
    ProgrammeSlug,
    ProgrammeStatus,
    SemesterId,
    SemesterName,
    SemesterNumber,
    SemesterStatus,
    TenantId,
    TenantName,
    TenantSlug,
    TenantStatus,
    UserId,
)
from app.infrastructure.db.models.tenant_core import (
    AcademicSessionModel,
    DepartmentModel,
    FacultyModel,
    LevelModel,
    MembershipModel,
    ProgrammeModel,
    SemesterModel,
    TenantModel,
)


def tenant_to_model(d: Tenant) -> TenantModel:
    return TenantModel(
        id=d.id.value,
        name=d.name.value,
        slug=d.slug.value,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def tenant_to_domain(m: TenantModel) -> Tenant:
    return Tenant(
        id=TenantId(m.id),
        name=TenantName(m.name),
        slug=TenantSlug(m.slug),
        status=TenantStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def faculty_to_model(d: Faculty) -> FacultyModel:
    return FacultyModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        name=d.name.value,
        slug=d.slug.value,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def faculty_to_domain(m: FacultyModel) -> Faculty:
    return Faculty(
        id=FacultyId(m.id),
        tenant_id=TenantId(m.tenant_id),
        name=FacultyName(m.name),
        slug=FacultySlug(m.slug),
        status=FacultyStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def department_to_model(d: Department) -> DepartmentModel:
    return DepartmentModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        faculty_id=d.faculty_id.value,
        name=d.name.value,
        slug=d.slug.value,
        code=d.code.value,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def department_to_domain(m: DepartmentModel) -> Department:
    return Department(
        id=DepartmentId(m.id),
        tenant_id=TenantId(m.tenant_id),
        faculty_id=FacultyId(m.faculty_id),
        name=DepartmentName(m.name),
        slug=DepartmentSlug(m.slug),
        code=DepartmentCode(m.code),
        status=DepartmentStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def programme_to_model(d: Programme) -> ProgrammeModel:
    return ProgrammeModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        faculty_id=d.faculty_id.value,
        department_id=d.department_id.value,
        name=d.name.value,
        slug=d.slug.value,
        code=d.code.value,
        duration_years=d.duration_years,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def programme_to_domain(m: ProgrammeModel) -> Programme:
    return Programme(
        id=ProgrammeId(m.id),
        tenant_id=TenantId(m.tenant_id),
        faculty_id=FacultyId(m.faculty_id),
        department_id=DepartmentId(m.department_id),
        name=ProgrammeName(m.name),
        slug=ProgrammeSlug(m.slug),
        code=ProgrammeCode(m.code),
        duration_years=m.duration_years,
        status=ProgrammeStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def level_to_model(d: Level) -> LevelModel:
    return LevelModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        code=d.code.value,
        name=d.name.value,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def level_to_domain(m: LevelModel) -> Level:
    return Level(
        id=LevelId(m.id),
        tenant_id=TenantId(m.tenant_id),
        code=LevelCode(m.code),
        name=LevelName(m.name),
        status=LevelStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def session_to_model(d: AcademicSession) -> AcademicSessionModel:
    return AcademicSessionModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        name=d.name.value,
        slug=d.slug.value,
        start_date=d.start_date,
        end_date=d.end_date,
        is_current=d.is_current,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def session_to_domain(m: AcademicSessionModel) -> AcademicSession:
    return AcademicSession(
        id=AcademicSessionId(m.id),
        tenant_id=TenantId(m.tenant_id),
        name=AcademicSessionName(m.name),
        slug=AcademicSessionSlug(m.slug),
        start_date=m.start_date,
        end_date=m.end_date,
        is_current=m.is_current,
        status=AcademicSessionStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def semester_to_model(d: Semester) -> SemesterModel:
    return SemesterModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        academic_session_id=d.academic_session_id.value,
        number=d.number.value,
        name=d.name.value,
        start_date=d.start_date,
        end_date=d.end_date,
        is_current=d.is_current,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def semester_to_domain(m: SemesterModel) -> Semester:
    return Semester(
        id=SemesterId(m.id),
        tenant_id=TenantId(m.tenant_id),
        academic_session_id=AcademicSessionId(m.academic_session_id),
        number=SemesterNumber(m.number),
        name=SemesterName(m.name),
        start_date=m.start_date,
        end_date=m.end_date,
        is_current=m.is_current,
        status=SemesterStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def membership_to_model(d: Membership) -> MembershipModel:
    return MembershipModel(
        id=d.id.value,
        tenant_id=d.tenant_id.value,
        user_id=d.user_id.value,
        role=d.role.value,
        status=d.status.value,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def membership_to_domain(m: MembershipModel) -> Membership:
    return Membership(
        id=MembershipId(m.id),
        tenant_id=TenantId(m.tenant_id),
        user_id=UserId(m.user_id),
        role=MembershipRole(m.role),
        status=MembershipStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )
