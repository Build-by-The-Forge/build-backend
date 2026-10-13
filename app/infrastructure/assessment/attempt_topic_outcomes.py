"""Graded outcomes of one attempt, by topic (M5 learning memory, ruling R3).

Reads the stored result breakdown and maps each answered question to its
topic title (or its topic id when the topic has no row), in the attempt's
tenant and for the attempt's own user only.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.domain.ai.assistant import MAX_MEMORY_TOPIC, MemoryObservation
from app.infrastructure.db.models.assessment import (
    AssessmentAttemptResultModel,
    AssessmentQuestionModel,
    QuestionModel,
)
from app.infrastructure.db.models.catalogue import TopicModel


class SqlAlchemyAttemptTopicOutcomes:
    def __init__(self, session_factory: Callable[[], AsyncSession] = SessionLocal) -> None:
        self._session_factory = session_factory

    async def outcomes(self, tenant_id: str, attempt_id: str, user_id: str) -> list[MemoryObservation]:
        async with self._session_factory() as session:
            result = await session.scalar(
                select(AssessmentAttemptResultModel).where(
                    AssessmentAttemptResultModel.tenant_id == tenant_id,
                    AssessmentAttemptResultModel.attempt_id == attempt_id,
                    AssessmentAttemptResultModel.user_id == user_id,
                )
            )
            if result is None:
                return []
            answered = [
                item for item in json.loads(result.breakdown_json or "[]") if item.get("selected_option_index") is not None
            ]
            if not answered:
                return []
            rows = await session.execute(
                select(AssessmentQuestionModel.id, QuestionModel.topic_id, TopicModel.title)
                .join(QuestionModel, QuestionModel.id == AssessmentQuestionModel.question_id)
                .outerjoin(TopicModel, TopicModel.id == QuestionModel.topic_id)
                .where(
                    AssessmentQuestionModel.id.in_([item["assessment_question_id"] for item in answered]),
                    QuestionModel.tenant_id == tenant_id,
                )
            )
            topics = {aq_id: (title or topic_id) for aq_id, topic_id, title in rows.all()}
        return [
            MemoryObservation(
                topic=topics[item["assessment_question_id"]][:MAX_MEMORY_TOPIC],
                correct=bool(item["is_correct"]),
            )
            for item in answered
            if topics.get(item["assessment_question_id"])
        ]
