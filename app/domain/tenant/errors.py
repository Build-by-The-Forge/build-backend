from __future__ import annotations


class TenantDomainError(Exception):
    pass


class InvalidTenantSlugError(TenantDomainError):
    pass


class InvalidTenantNameError(TenantDomainError):
    pass


class TenantAlreadyArchivedError(TenantDomainError):
    pass
