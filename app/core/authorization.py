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
    ASSESSMENT_ATTEMPT_START = "assessment.attempt.start"
    ASSESSMENT_ATTEMPT_READ = "assessment.attempt.read"
    ASSESSMENT_ATTEMPT_SUBMIT = "assessment.attempt.submit"
    ASSESSMENT_ATTEMPT_ANSWER_WRITE = "assessment.attempt.answer.write"
    ASSESSMENT_ATTEMPT_ANSWER_DELETE = "assessment.attempt.answer.delete"
    ASSESSMENT_ATTEMPT_RESULT_READ = "assessment.attempt.result.read"
    ASSESSMENT_RESULT_READ = "assessment.result.read"
    CURRICULUM_SOURCE_READ = "curriculum.source.read"
    CURRICULUM_SOURCE_MANAGE = "curriculum.source.manage"
    CONTENT_SOURCE_READ = "content.source.read"
    CONTENT_SOURCE_MANAGE = "content.source.manage"
    CONTENT_ASSET_READ = "content.asset.read"
    CONTENT_ASSET_UPLOAD = "content.asset.upload"
    CONTENT_JOB_READ = "content.job.read"
    CONTENT_JOB_MANAGE = "content.job.manage"
    TENANT_MEMBER_READ = "tenant.member.read"
    TENANT_MEMBER_INVITE = "tenant.member.invite"
    TENANT_MEMBER_MANAGE = "tenant.member.manage"
    TENANT_SETTINGS_MANAGE = "tenant.settings.manage"
    # AI operations proxied to AI-service (design B.5). The backend checks
    # the permission and forwards exactly it in the signed context.
    AI_USE = "ai.use"
    AI_QUESTIONS_GENERATE = "ai.questions.generate"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "student": frozenset(
        {
            Permission.CATALOGUE_READ,
            Permission.ASSESSMENT_READ,
            Permission.ASSESSMENT_ATTEMPT_START,
            Permission.ASSESSMENT_ATTEMPT_READ,
            Permission.ASSESSMENT_ATTEMPT_SUBMIT,
            Permission.ASSESSMENT_ATTEMPT_ANSWER_WRITE,
            Permission.ASSESSMENT_ATTEMPT_ANSWER_DELETE,
            Permission.ASSESSMENT_ATTEMPT_RESULT_READ,
            Permission.CONTENT_SOURCE_READ,
            Permission.CONTENT_ASSET_READ,
            Permission.CONTENT_JOB_READ,
            Permission.AI_USE,
        }
    ),
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
            Permission.ASSESSMENT_ATTEMPT_RESULT_READ,
            Permission.ASSESSMENT_RESULT_READ,
            Permission.CURRICULUM_SOURCE_READ,
            Permission.CONTENT_SOURCE_READ,
            Permission.CONTENT_SOURCE_MANAGE,
            Permission.CONTENT_ASSET_READ,
            Permission.CONTENT_ASSET_UPLOAD,
            Permission.CONTENT_JOB_READ,
            Permission.CONTENT_JOB_MANAGE,
            Permission.AI_USE,
            Permission.AI_QUESTIONS_GENERATE,
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
            Permission.ASSESSMENT_ATTEMPT_RESULT_READ,
            Permission.ASSESSMENT_RESULT_READ,
            Permission.CURRICULUM_SOURCE_READ,
            Permission.CONTENT_SOURCE_READ,
            Permission.CONTENT_SOURCE_MANAGE,
            Permission.CONTENT_ASSET_READ,
            Permission.CONTENT_ASSET_UPLOAD,
            Permission.CONTENT_JOB_READ,
            Permission.CONTENT_JOB_MANAGE,
            Permission.AI_USE,
            Permission.AI_QUESTIONS_GENERATE,
            Permission.TENANT_MEMBER_READ,
            Permission.TENANT_MEMBER_INVITE,
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
            Permission.ASSESSMENT_ATTEMPT_RESULT_READ,
            Permission.ASSESSMENT_RESULT_READ,
            Permission.CURRICULUM_SOURCE_READ,
            Permission.CONTENT_SOURCE_READ,
            Permission.CONTENT_SOURCE_MANAGE,
            Permission.CONTENT_ASSET_READ,
            Permission.CONTENT_ASSET_UPLOAD,
            Permission.CONTENT_JOB_READ,
            Permission.CONTENT_JOB_MANAGE,
            Permission.AI_USE,
            Permission.AI_QUESTIONS_GENERATE,
            Permission.TENANT_MEMBER_READ,
            Permission.TENANT_MEMBER_INVITE,
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
