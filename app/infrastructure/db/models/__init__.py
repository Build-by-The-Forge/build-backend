import app.infrastructure.db.models.assessment  # noqa: F401
import app.infrastructure.db.models.catalogue  # noqa: F401
import app.infrastructure.db.models.content  # noqa: F401
import app.infrastructure.db.models.institutional_curriculum  # noqa: F401
import app.infrastructure.identity.models  # noqa: F401
from app.db.base import Base
from app.infrastructure.db.models.assessment import (
    AssessmentAttemptModel,
    AssessmentModel,
    AssessmentQuestionModel,
    QuestionModel,
    QuestionOptionModel,
)
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    CoursePrerequisiteModel,
    CurriculumVersionModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    TopicModel,
)
from app.infrastructure.db.models.content import (
    ContentAssetModel,
    ContentIngestionJobModel,
    ContentSourceModel,
)
from app.infrastructure.db.models.tenant_core import (
    AcademicSessionModel,
    DepartmentModel,
    FacultyModel,
    LevelModel,
    MembershipModel,
    ProgrammeModel,
    SemesterModel,
    TenantInvitationModel,
    TenantModel,
)

__all__ = [
    "Base",
    "TenantModel",
    "FacultyModel",
    "DepartmentModel",
    "ProgrammeModel",
    "LevelModel",
    "AcademicSessionModel",
    "SemesterModel",
    "MembershipModel",
    "TenantInvitationModel",
    "CourseModel",
    "CurriculumVersionModel",
    "TopicModel",
    "LearningOutcomeModel",
    "ReferenceMaterialModel",
    "CoursePrerequisiteModel",
    "AssessmentModel",
    "AssessmentAttemptModel",
    "AssessmentQuestionModel",
    "QuestionModel",
    "QuestionOptionModel",
    "ContentSourceModel",
    "ContentAssetModel",
    "ContentIngestionJobModel",
]
