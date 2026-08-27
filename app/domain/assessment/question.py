from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.assessment.errors import QuestionAlreadyArchivedError
from app.domain.assessment.value_objects import (
    Difficulty,
    QuestionDisplayOrder,
    QuestionExplanation,
    QuestionId,
    QuestionMarks,
    QuestionOptionId,
    QuestionOptionText,
    QuestionPrompt,
    QuestionStatus,
    QuestionType,
)


@dataclass(slots=True)
class DomainEvent:
    event_type: str
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class QuestionOption:
    id: QuestionOptionId
    question_id: QuestionId
    text: QuestionOptionText
    display_order: QuestionDisplayOrder
    is_correct: bool = False


@dataclass
class Question:
    id: QuestionId
    tenant_id: str
    topic_id: str
    learning_outcome_id: str | None
    question_type: QuestionType
    prompt: QuestionPrompt
    explanation: QuestionExplanation | None
    difficulty: Difficulty = Difficulty.MEDIUM
    marks: QuestionMarks = QuestionMarks(1)
    status: QuestionStatus = QuestionStatus.DRAFT
    options: list[QuestionOption] = field(default_factory=list, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        topic_id: str,
        learning_outcome_id: str | None = None,
        question_type: QuestionType,
        prompt: QuestionPrompt,
        explanation: QuestionExplanation | None = None,
        difficulty: Difficulty = Difficulty.MEDIUM,
        marks: QuestionMarks = QuestionMarks(1),
        options: list[QuestionOption] | None = None,
        question_id: QuestionId | None = None,
    ) -> "Question":
        normalized_options = list(options or [])
        if len(normalized_options) < 2:
            raise ValueError("question must have at least 2 options")

        correct_options = [option for option in normalized_options if option.is_correct]
        if len(correct_options) != 1:
            raise ValueError("MCQ questions require exactly one correct option")

        seen_orders: set[int] = set()
        for option in normalized_options:
            if option.display_order.value in seen_orders:
                raise ValueError(
                    "question options must have unique display order values"
                )
            seen_orders.add(option.display_order.value)
            if not option.text.value.strip():
                raise ValueError("question option text must be a non-empty string")

        question = cls(
            id=question_id or QuestionId(""),
            tenant_id=tenant_id,
            topic_id=topic_id,
            learning_outcome_id=learning_outcome_id,
            question_type=question_type,
            prompt=prompt,
            explanation=explanation,
            difficulty=difficulty,
            marks=marks,
            status=QuestionStatus.DRAFT,
            options=normalized_options,
        )
        for option in question.options:
            option.question_id = question.id
        question._events.append(
            DomainEvent(
                event_type="question.created",
                payload={
                    "question_id": question.id.value,
                    "tenant_id": question.tenant_id,
                    "topic_id": question.topic_id,
                    "question_type": question.question_type.value,
                },
            )
        )
        return question

    def archive(self) -> None:
        if self.status == QuestionStatus.ARCHIVED:
            raise QuestionAlreadyArchivedError("question already archived")
        self.status = QuestionStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="question.archived",
                payload={"question_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == QuestionStatus.ARCHIVED:
            raise QuestionAlreadyArchivedError("question already archived")
        if self.status == QuestionStatus.PUBLISHED:
            return
        self.status = QuestionStatus.PUBLISHED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="question.published",
                payload={"question_id": self.id.value},
            )
        )

    def update_details(
        self,
        *,
        prompt: QuestionPrompt | None = None,
        explanation: QuestionExplanation | None = None,
        difficulty: Difficulty | None = None,
        marks: QuestionMarks | None = None,
    ) -> None:
        if self.status == QuestionStatus.ARCHIVED:
            raise QuestionAlreadyArchivedError("question already archived")

        changed = False
        if prompt is not None and prompt != self.prompt:
            self.prompt = prompt
            changed = True
        if explanation is not None and explanation != self.explanation:
            self.explanation = explanation
            changed = True
        if difficulty is not None and difficulty != self.difficulty:
            self.difficulty = difficulty
            changed = True
        if marks is not None and marks != self.marks:
            self.marks = marks
            changed = True

        if not changed:
            return

        self.touch()
        self._events.append(
            DomainEvent(
                event_type="question.updated",
                payload={"question_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    @property
    def is_published(self) -> bool:
        return self.status == QuestionStatus.PUBLISHED
