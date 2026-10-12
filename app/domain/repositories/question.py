from typing import Protocol

from app.domain.assessment.question import Question


class QuestionRepository(Protocol):
    async def save(self, question: Question, tenant_id: str | None = None) -> Question:
        raise NotImplementedError

    async def get_by_id(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        raise NotImplementedError

    async def list_by_topic(self, topic_id: str, tenant_id: str | None = None) -> list[Question]:
        raise NotImplementedError

    async def list_by_learning_outcome(self, learning_outcome_id: str, tenant_id: str | None = None) -> list[Question]:
        raise NotImplementedError

    async def list_all(self, tenant_id: str | None = None) -> list[Question]:
        raise NotImplementedError

    async def update(self, question: Question, tenant_id: str | None = None) -> Question:
        raise NotImplementedError
