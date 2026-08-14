from pydantic import BaseModel, Field


class CreateCourseRequest(BaseModel):
    tenant_id: str | None = Field(default=None)
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
