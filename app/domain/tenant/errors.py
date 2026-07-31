from __future__ import annotations


class TenantDomainError(Exception):
    pass


class TenantAlreadyArchivedError(TenantDomainError):
    pass


class FacultyAlreadyArchivedError(TenantDomainError):
    pass


class DepartmentAlreadyArchivedError(TenantDomainError):
    pass


class ProgrammeAlreadyArchivedError(TenantDomainError):
    pass


class LevelAlreadyArchivedError(TenantDomainError):
    pass


class AcademicSessionAlreadyArchivedError(TenantDomainError):
    pass


class SemesterAlreadyArchivedError(TenantDomainError):
    pass
