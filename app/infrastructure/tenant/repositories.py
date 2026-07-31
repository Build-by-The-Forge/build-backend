from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.domain.tenant.academic_session import AcademicSession
from app.domain.tenant.department import Department
from app.domain.tenant.faculty import Faculty
from app.domain.tenant.level import Level
from app.domain.tenant.membership import Membership
from app.domain.tenant.programme import Programme
from app.domain.tenant.semester import Semester
from app.domain.tenant.tenant import Tenant
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
from app.infrastructure.tenant.mappers import (
    department_to_domain,
    department_to_model,
    faculty_to_domain,
    faculty_to_model,
    level_to_domain,
    level_to_model,
    membership_to_domain,
    membership_to_model,
    programme_to_domain,
    programme_to_model,
    semester_to_domain,
    semester_to_model,
    session_to_domain,
    session_to_model,
    tenant_to_domain,
    tenant_to_model,
)


class SqlAlchemyTenantRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, tenant: Tenant) -> None:
        self.session.add(tenant_to_model(tenant))

    def get_by_id(self, tenant_id: str) -> Optional[Tenant]:
        m = self.session.get(TenantModel, tenant_id)
        return tenant_to_domain(m) if m else None

    def get_by_slug(self, slug: str) -> Optional[Tenant]:
        m = self.session.query(TenantModel).filter_by(slug=slug).first()
        return tenant_to_domain(m) if m else None

    def list_all(self) -> List[Tenant]:
        return [tenant_to_domain(m) for m in self.session.query(TenantModel).all()]


class SqlAlchemyFacultyRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, f: Faculty) -> None:
        self.session.add(faculty_to_model(f))

    def get_by_id(self, fid: str) -> Optional[Faculty]:
        m = self.session.get(FacultyModel, fid)
        return faculty_to_domain(m) if m else None

    def list_by_tenant(self, tenant_id: str) -> List[Faculty]:
        return [faculty_to_domain(m) for m in self.session.query(FacultyModel).filter_by(tenant_id=tenant_id).all()]


class SqlAlchemyDepartmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, d: Department) -> None:
        self.session.add(department_to_model(d))

    def get_by_id(self, did: str) -> Optional[Department]:
        m = self.session.get(DepartmentModel, did)
        return department_to_domain(m) if m else None

    def list_by_faculty(self, fid: str) -> List[Department]:
        return [department_to_domain(m) for m in self.session.query(DepartmentModel).filter_by(faculty_id=fid).all()]

    def list_by_tenant(self, tid: str) -> List[Department]:
        return [department_to_domain(m) for m in self.session.query(DepartmentModel).filter_by(tenant_id=tid).all()]


class SqlAlchemyProgrammeRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, p: Programme) -> None:
        self.session.add(programme_to_model(p))

    def list_by_department(self, dept_id: str) -> List[Programme]:
        return [programme_to_domain(m) for m in self.session.query(ProgrammeModel).filter_by(department_id=dept_id).all()]


class SqlAlchemyLevelRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, l: Level) -> None:
        self.session.add(level_to_model(l))

    def list_by_tenant(self, tid: str) -> List[Level]:
        return [level_to_domain(m) for m in self.session.query(LevelModel).filter_by(tenant_id=tid).all()]


class SqlAlchemyAcademicSessionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, s: AcademicSession) -> None:
        self.session.add(session_to_model(s))

    def list_by_tenant(self, tid: str) -> List[AcademicSession]:
        return [session_to_domain(m) for m in self.session.query(AcademicSessionModel).filter_by(tenant_id=tid).all()]

    def get_current(self, tid: str) -> Optional[AcademicSession]:
        m = self.session.query(AcademicSessionModel).filter_by(tenant_id=tid, is_current=True).first()
        return session_to_domain(m) if m else None


class SqlAlchemySemesterRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, s: Semester) -> None:
        self.session.add(semester_to_model(s))

    def list_by_session(self, sid: str) -> List[Semester]:
        return [semester_to_domain(m) for m in self.session.query(SemesterModel).filter_by(academic_session_id=sid).all()]


class SqlAlchemyMembershipRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, m: Membership) -> None:
        self.session.add(membership_to_model(m))

    def get_by_tenant_user(self, tid: str, uid: str) -> Optional[Membership]:
        mod = self.session.query(MembershipModel).filter_by(tenant_id=tid, user_id=uid).first()
        return membership_to_domain(mod) if mod else None
