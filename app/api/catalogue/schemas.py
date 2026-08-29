from pydantic import BaseModel, ConfigDict, Field

from app.domain.catalogue.value_objects import ReferenceMaterialType


class CreateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    description: str | None = None


class CourseResponse(BaseModel):
    id: str
    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    status: str
    description: str | None = None


class UpdateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None


class CreateTopicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    slug: str
    description: str | None = None
    sequence: int = 1


class UpdateTopicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None


class CreateLearningOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = 1
    description: str


class UpdateLearningOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None


class CreateReferenceMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    material_type: ReferenceMaterialType
    url: str | None = None


class UpdateReferenceMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200)
    material_type: ReferenceMaterialType | None = None
    url: str | None = None
