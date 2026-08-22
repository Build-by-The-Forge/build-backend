from pydantic import BaseModel, ConfigDict


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
