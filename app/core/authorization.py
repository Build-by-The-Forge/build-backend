from enum import StrEnum

from app.core.tenant_context import TenantContext


class Permission(StrEnum):
    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_CREATE = "catalogue.create"
    CATALOGUE_UPDATE = "catalogue.update"
    CATALOGUE_ARCHIVE = "catalogue.archive"
    CATALOGUE_PUBLISH = "catalogue.publish"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "student": frozenset({Permission.CATALOGUE_READ}),
    "lecturer": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
        }
    ),
    "hod": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
        }
    ),
    "faculty_admin": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
            Permission.CATALOGUE_ARCHIVE,
            Permission.CATALOGUE_PUBLISH,
        }
    ),
    "admin": frozenset(Permission),
    "owner": frozenset(Permission),
}


class AuthorizationService:
    def permissions_for(self, context: TenantContext) -> frozenset[Permission]:
        return ROLE_PERMISSIONS.get(context.role, frozenset())

    def can(self, context: TenantContext, permission: Permission) -> bool:
        return permission in self.permissions_for(context)


authorization = AuthorizationService()