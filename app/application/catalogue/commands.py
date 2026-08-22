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


@dataclass(slots=True)
class CreateTopicCommand:
    course_id: str
    title: str
    slug: str
    description: str | None = None
    sequence: int = 1
    tenant_id: str | None = None


@dataclass(slots=True)
class UpdateTopicCommand:
    topic_id: str
    title: str | None = None
    description: str | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class CreateLearningOutcomeCommand:
    topic_id: str
    sequence: int
    description: str
    tenant_id: str | None = None


@dataclass(slots=True)
class UpdateLearningOutcomeCommand:
    learning_outcome_id: str
    description: str | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class CreateReferenceMaterialCommand:
    topic_id: str
    title: str
    material_type: str
    url: str | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class UpdateReferenceMaterialCommand:
    reference_material_id: str
    title: str | None = None
    material_type: str | None = None
    url: str | None = None
    tenant_id: str | None = None
