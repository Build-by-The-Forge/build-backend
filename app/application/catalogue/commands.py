from dataclasses import dataclass


@dataclass(slots=True)
class CreateCourseCommand:
    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    description: str | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class UpdateCourseCommand:
    course_id: str
    title: str | None = None
    description: str | None = None
    tenant_id: str | None = None
