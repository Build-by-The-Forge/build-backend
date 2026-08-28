from typing import Protocol

from app.domain.assessment.attempt_answer import AttemptAnswer


class AttemptAnswerRepository(Protocol):
    async def get_by_attempt_and_question(
        self,
        attempt_id: str,
        assessment_question_id: str,
        tenant_id: str,
    ) -> AttemptAnswer | None:
        raise NotImplementedError

    async def list_by_attempt(
        self, attempt_id: str, tenant_id: str
    ) -> list[AttemptAnswer]:
        raise NotImplementedError

    async def save(self, answer: AttemptAnswer) -> AttemptAnswer:
        raise NotImplementedError

    async def delete(self, answer: AttemptAnswer) -> None:
        raise NotImplementedError