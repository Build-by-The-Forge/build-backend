# ensure identity models are also imported for metadata
import app.infrastructure.identity.models  # noqa: F401
from app.db.base import Base
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
]
