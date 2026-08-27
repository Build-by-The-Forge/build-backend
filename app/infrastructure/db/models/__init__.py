# ensure identity models are also imported for metadata
import app.infrastructure.db.models.catalogue  # noqa: F401
import app.infrastructure.identity.models  # noqa: F401
from app.db.base import Base
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    CoursePrerequisiteModel,
    CurriculumVersionModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    TopicModel,
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
    "CourseModel",
    "CurriculumVersionModel",
    "TopicModel",
    "LearningOutcomeModel",
    "ReferenceMaterialModel",
    "CoursePrerequisiteModel",
]
