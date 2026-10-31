from dataclasses import dataclass

from app.domain.assessment.attempt_policy import AttemptPolicy


@dataclass(slots=True)
class CreateAssessmentCommand:
    tenant_id: str
    course_id: str
    title: str
    instructions: str
    duration_minutes: int
    passing_score: int = 0
    attempt_policy: AttemptPolicy | None = None


@dataclass(slots=True)
class GetAssessmentCommand:
    assessment_id: str
    tenant_id: str


@dataclass(slots=True)
class ListAssessmentsCommand:
    tenant_id: str
    course_id: str | None = None


@dataclass(slots=True)
class UpdateAssessmentCommand:
    assessment_id: str
    tenant_id: str
    title: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    passing_score: int | None = None
    attempt_policy: AttemptPolicy | None = None


@dataclass(slots=True)
class PublishAssessmentCommand:
    assessment_id: str
    tenant_id: str


@dataclass(slots=True)
class AddQuestionToAssessmentCommand:
    assessment_id: str
    question_id: str
    tenant_id: str


@dataclass(slots=True)
class GetAssessmentResultsCommand:
    assessment_id: str
    tenant_id: str
    limit: int = 50
    offset: int = 0
