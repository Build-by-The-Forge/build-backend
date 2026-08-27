from enum import StrEnum

from app.core.tenant_context import TenantContext


class Permission(StrEnum):
    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_CREATE = "catalogue.create"
    CATALOGUE_UPDATE = "catalogue.update"
    CATALOGUE_ARCHIVE = "catalogue.archive"
    CATALOGUE_PUBLISH = "catalogue.publish"
    ASSESSMENT_READ = "assessment.read"
    ASSESSMENT_CREATE = "assessment.create"
    ASSESSMENT_UPDATE = "assessment.update"
    ASSESSMENT_PUBLISH = "assessment.publish"
    ASSESSMENT_QUESTION_CREATE = "assessment.question.create"
    ASSESSMENT_QUESTION_UPDATE = "assessment.question.update"
    ASSESSMENT_QUESTION_PUBLISH = "assessment.question.publish"
    ASSESSMENT_QUESTION_ARCHIVE = "assessment.question.archive"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "student": frozenset({Permission.CATALOGUE_READ}),
    "lecturer": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
            Permission.ASSESSMENT_READ,
            Permission.ASSESSMENT_CREATE,
            Permission.ASSESSMENT_UPDATE,
            Permission.ASSESSMENT_PUBLISH,
            Permission.ASSESSMENT_QUESTION_CREATE,
            Permission.ASSESSMENT_QUESTION_UPDATE,
            Permission.ASSESSMENT_QUESTION_PUBLISH,
            Permission.ASSESSMENT_QUESTION_ARCHIVE,
        }
    ),
    "hod": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
            Permission.ASSESSMENT_READ,
            Permission.ASSESSMENT_CREATE,
            Permission.ASSESSMENT_UPDATE,
            Permission.ASSESSMENT_PUBLISH,
            Permission.ASSESSMENT_QUESTION_CREATE,
            Permission.ASSESSMENT_QUESTION_UPDATE,
            Permission.ASSESSMENT_QUESTION_PUBLISH,
            Permission.ASSESSMENT_QUESTION_ARCHIVE,
        }
    ),
    "faculty_admin": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.CATALOGUE_CREATE,
            Permission.CATALOGUE_UPDATE,
            Permission.CATALOGUE_ARCHIVE,
            Permission.CATALOGUE_PUBLISH,
            Permission.ASSESSMENT_READ,
            Permission.ASSESSMENT_CREATE,
            Permission.ASSESSMENT_UPDATE,
            Permission.ASSESSMENT_PUBLISH,
            Permission.ASSESSMENT_QUESTION_CREATE,
            Permission.ASSESSMENT_QUESTION_UPDATE,
            Permission.ASSESSMENT_QUESTION_PUBLISH,
            Permission.ASSESSMENT_QUESTION_ARCHIVE,
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
