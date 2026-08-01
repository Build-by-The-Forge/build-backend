from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

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
    def __init__(self, session_factory: Callable[[], Session]):
        self._factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> TenantUnitOfWork:
        self.session = self._factory()
        self.tenants = SqlAlchemyTenantRepository(self.session)
        self.faculties = SqlAlchemyFacultyRepository(self.session)
        self.departments = SqlAlchemyDepartmentRepository(self.session)
        self.programmes = SqlAlchemyProgrammeRepository(self.session)
        self.levels = SqlAlchemyLevelRepository(self.session)
        self.sessions = SqlAlchemyAcademicSessionRepository(self.session)
        self.semesters = SqlAlchemySemesterRepository(self.session)
        self.memberships = SqlAlchemyMembershipRepository(self.session)
        return self

    def __exit__(self, *args: object) -> None:
        if self.session:
            try:
                self.session.rollback()
            finally:
                self.session.close()

    def commit(self) -> None:
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        if self.session:
            self.session.rollback()
