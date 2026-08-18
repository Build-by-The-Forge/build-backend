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
