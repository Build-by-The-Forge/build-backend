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
