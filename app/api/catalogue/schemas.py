from typing import Annotated

from fastapi import Path, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.catalogue.value_objects import ReferenceMaterialType

# PostgreSQL can't hold a NUL in text or compare against one, and answers with an error.
_NO_NUL = r"^[^\x00]*$"
Text = Annotated[str, StringConstraints(pattern=_NO_NUL)]
IdInPath = Annotated[str, Path(pattern=_NO_NUL)]
IdFilter = Annotated[str | None, Query(pattern=_NO_NUL)]
# The sequence columns are 32-bit integers. The domain sets the lower bound's rule.
Sequence = Annotated[int, Field(le=2_147_483_647, ge=-2_147_483_648)]


class CreateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: Text
    code: Text
    title: Text
    slug: Text
    credit_units: int
    level: int
    semester: int
    description: Text | None = None


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

    title: Text | None = None
    description: Text | None = None


class CreateTopicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Text
    slug: Text
    description: Text | None = None
    sequence: Sequence = 1


class UpdateTopicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Text | None = None
    description: Text | None = None


class CreateLearningOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: Sequence = 1
    description: Text


class UpdateLearningOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Text | None = None


class CreateReferenceMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200, pattern=_NO_NUL)
    material_type: ReferenceMaterialType
    url: str | None = Field(default=None, max_length=1024, pattern=_NO_NUL)


class UpdateReferenceMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200, pattern=_NO_NUL)
    material_type: ReferenceMaterialType | None = None
    url: str | None = Field(default=None, max_length=1024, pattern=_NO_NUL)
