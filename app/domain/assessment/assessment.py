from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from app.domain.assessment.errors import AssessmentAlreadyArchivedError
from app.events.base import DomainEvent


class AssessmentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


@dataclass(slots=True)
class AssessmentQuestion:
    question_id: str
    prompt: str
    options: list[str]
    marks: int = 1

    def __post_init__(self) -> None:
        if not self.question_id or not self.question_id.strip():
            raise ValueError("question_id is required")
        if not self.prompt.strip():
            raise ValueError("question prompt cannot be empty")
        if not self.options:
            raise ValueError("question must contain at least one option")
        if self.marks <= 0:
            raise ValueError("question marks must be positive")


@dataclass
class Assessment:
    tenant_id: str
    course_id: str
    title: str
    instructions: str
    duration_minutes: int
    passing_score: int = 0
    status: AssessmentStatus = AssessmentStatus.DRAFT
    questions: list[AssessmentQuestion] = field(default_factory=list, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.course_id.strip():
            raise ValueError("course_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.instructions.strip():
            raise ValueError("instructions are required")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.passing_score < 0:
            raise ValueError("passing_score cannot be negative")

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        course_id: str,
        title: str,
        instructions: str,
        duration_minutes: int,
        passing_score: int,
    ) -> "Assessment":
        assessment = cls(
            tenant_id=tenant_id,
            course_id=course_id,
            title=title,
            instructions=instructions,
            duration_minutes=duration_minutes,
            passing_score=passing_score,
        )
        assessment._events.append(
            DomainEvent(
                event_type="assessment.created",
                payload={
                    "tenant_id": assessment.tenant_id,
                    "course_id": assessment.course_id,
                    "assessment_id": assessment.id,
                },
            )
        )
        return assessment

    @property
    def id(self) -> str:
        return f"assessment-{self.created_at.timestamp():.0f}-{self.tenant_id}-{self.course_id}"

    @property
    def pass_mark(self) -> int:
        return self.passing_score

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def add_question(
        self,
        question_id: str,
        prompt: str,
        options: list[str],
        marks: int = 1,
    ) -> AssessmentQuestion:
        if self.status == AssessmentStatus.ARCHIVED:
            raise AssessmentAlreadyArchivedError("assessment already archived")
        if any(existing.question_id == question_id for existing in self.questions):
            raise ValueError(
                f"question {question_id} already exists in this assessment"
            )

        item = AssessmentQuestion(
            question_id=question_id,
            prompt=prompt,
            options=list(options),
            marks=marks,
        )
        self.questions.append(item)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="assessment.question_added",
                payload={
                    "assessment_id": self.id,
                    "question_id": question_id,
                    "marks": marks,
                },
            )
        )
        return item

    def publish(self) -> None:
        if self.status == AssessmentStatus.ARCHIVED:
            raise AssessmentAlreadyArchivedError("assessment already archived")
        if self.status == AssessmentStatus.PUBLISHED:
            return
        if self.status == AssessmentStatus.OPEN:
            raise ValueError("assessment cannot be republished while open")
        self.status = AssessmentStatus.PUBLISHED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="assessment.published",
                payload={"assessment_id": self.id, "status": self.status.value},
            )
        )

    def open(self) -> None:
        if self.status == AssessmentStatus.ARCHIVED:
            raise AssessmentAlreadyArchivedError("assessment already archived")
        if self.status not in {AssessmentStatus.PUBLISHED, AssessmentStatus.OPEN}:
            raise ValueError("assessment must be published before opening")
        self.status = AssessmentStatus.OPEN
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="assessment.opened",
                payload={"assessment_id": self.id, "status": self.status.value},
            )
        )

    def close(self) -> None:
        if self.status == AssessmentStatus.ARCHIVED:
            raise AssessmentAlreadyArchivedError("assessment already archived")
        if self.status != AssessmentStatus.OPEN:
            raise ValueError("assessment must be open before closing")
        self.status = AssessmentStatus.CLOSED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="assessment.closed",
                payload={"assessment_id": self.id, "status": self.status.value},
            )
        )

    def archive(self) -> None:
        if self.status == AssessmentStatus.ARCHIVED:
            raise AssessmentAlreadyArchivedError("assessment already archived")
        self.status = AssessmentStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="assessment.archived",
                payload={"assessment_id": self.id, "status": self.status.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
