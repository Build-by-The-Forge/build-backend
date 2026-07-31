from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.tenant.repositories import (
    SqlAlchemyAcademicSessionRepository,
    SqlAlchemyDepartmentRepository,
    SqlAlchemyFacultyRepository,
    SqlAlchemyLevelRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyProgrammeRepository,
    SqlAlchemySemesterRepository,
    SqlAlchemyTenantRepository,
)


class TenantUnitOfWork:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> TenantUnitOfWork:
        self.session = self.session_factory()
        self.tenants = SqlAlchemyTenantRepository(self.session)
        self.faculties = SqlAlchemyFacultyRepository(self.session)
        self.departments = SqlAlchemyDepartmentRepository(self.session)
        self.programmes = SqlAlchemyProgrammeRepository(self.session)
        self.levels = SqlAlchemyLevelRepository(self.session)
        self.sessions = SqlAlchemyAcademicSessionRepository(self.session)
        self.semesters = SqlAlchemySemesterRepository(self.session)
        self.memberships = SqlAlchemyMembershipRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
