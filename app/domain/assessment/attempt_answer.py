from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class AttemptAnswer:
    tenant_id: str
    attempt_id: str
    assessment_question_id: str
    selected_option_index: int
    answer_id: str = field(default_factory=lambda: f"answer-{uuid4()}", repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.attempt_id.strip():
            raise ValueError("attempt_id is required")
        if not self.assessment_question_id.strip():
            raise ValueError("assessment_question_id is required")
        if self.selected_option_index < 0:
            raise ValueError("selected_option_index must be non-negative")

    @property
    def id(self) -> str:
        return self.answer_id

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        attempt_id: str,
        assessment_question_id: str,
        selected_option_index: int,
    ) -> "AttemptAnswer":
        answer = cls(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            assessment_question_id=assessment_question_id,
            selected_option_index=selected_option_index,
        )
        return answer

    def update_selection(
        self, selected_option_index: int, *, option_count: int
    ) -> None:
        if selected_option_index < 0:
            raise ValueError("selected_option_index must be non-negative")
        if selected_option_index >= option_count:
            raise ValueError("selected_option_index is outside the valid option range")

        self.selected_option_index = selected_option_index
        self.updated_at = datetime.now(timezone.utc)
