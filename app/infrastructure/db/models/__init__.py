# ensure identity models are also imported for metadata
import app.infrastructure.identity.models  # noqa: F401
from app.db.base import Base
import app.infrastructure.db.models.catalogue  # noqa: F401
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    CurriculumVersionModel,
    TopicModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    CoursePrerequisiteModel,
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
