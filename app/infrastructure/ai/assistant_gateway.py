"""Signed calls to AI-service's /v1/ai routes (design B.4, B.5).

Each request is signed with BUILD Service Signature v1 and a user context
carrying exactly the permission the backend checked. The body has no
identity fields. Redirects are never followed. AI-service's error detail is
logged, never returned to the client.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from app.core.config import settings
from app.domain.ai.assistant import (
    AIActor,
    AIAssistantError,
    AIAssistantGateway,
    ChatAnswer,
    Explanation,
    GeneratedQuestions,
    MemoryItem,
    MemoryObservation,
    parse_generated_question,
)
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import Direction, ServiceKeys, sign_request

logger = logging.getLogger(__name__)


class HttpAIAssistantGateway(AIAssistantGateway):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
        keys: ServiceKeys | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._timeout = float(timeout_seconds or settings.ai_service_timeout_seconds)
        self._client = client
        self._keys_override = keys

    def _keys(self) -> ServiceKeys:
        if self._keys_override is not None:
            return self._keys_override
        if not settings.backend_to_ai_secret:
            raise AIAssistantError(
                "BACKEND_TO_AI_SECRET is not configured",
                error_code="AI_SERVICE_NOT_CONFIGURED",
                unavailable=True,
            )
        return ServiceKeys(current=settings.backend_to_ai_secret)

    async def chat(self, actor: AIActor, message: str) -> ChatAnswer:
        data = await self._post("/v1/ai/chat", {"message": message}, actor)
        answer = data.get("answer")
        context = data.get("context_used", [])
        if not isinstance(answer, str) or not isinstance(context, list):
            raise _bad_response("chat")
        texts = [item["text"] for item in context if isinstance(item, dict) and isinstance(item.get("text"), str)]
        return ChatAnswer(answer=answer, context=texts)

    async def explain(self, actor: AIActor, subject: str) -> Explanation:
        data = await self._post("/v1/ai/explain", {"subject": subject}, actor)
        explanation = data.get("explanation")
        if not isinstance(explanation, str):
            raise _bad_response("explain")
        return Explanation(explanation=explanation)

    async def generate_questions(
        self, actor: AIActor, topic: str, count: int, difficulty: str, question_type: str
    ) -> GeneratedQuestions:
        data = await self._post(
            "/v1/ai/generate-questions",
            {"topic": topic, "count": count, "difficulty": difficulty, "question_type": question_type},
            actor,
        )
        items, discarded = data.get("questions"), data.get("discarded")
        if not isinstance(items, list) or not isinstance(discarded, int) or discarded < 0:
            raise _bad_response("generate-questions")
        accepted = []
        for item in items[:count]:
            question = parse_generated_question(item)
            # Only what was asked for, by the backend's own rules.
            if question is None or (question.question_type, question.difficulty) != (question_type, difficulty):
                discarded += 1
            else:
                accepted.append(question)
        discarded += max(len(items) - count, 0)
        return GeneratedQuestions(questions=accepted, discarded=discarded)

    async def query_memory(self, actor: AIActor, topics: list[str] | None = None) -> list[MemoryItem]:
        payload: dict[str, Any] = {} if topics is None else {"topics": topics}
        return _memory_items(await self._post("/v1/ai/memory/query", payload, actor))

    async def record_memory(self, actor: AIActor, observations: list[MemoryObservation]) -> list[MemoryItem]:
        payload = {"observations": [{"topic": o.topic, "correct": o.correct} for o in observations]}
        return _memory_items(await self._post("/v1/ai/memory/upsert", payload, actor))

    async def _post(self, path: str, payload: dict[str, Any], actor: AIActor) -> dict[str, Any]:
        keys = self._keys()
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        url = httpx.URL(f"{self._base_url}{path}")
        headers = sign_request(
            direction=Direction.BACKEND_TO_AI,
            keys=keys,
            method="POST",
            target=url.raw_path.decode("ascii"),
            body=body,
            context=ServiceContext.for_user(
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                membership_id=actor.membership_id,
                role=actor.role,
                permissions=[actor.permission],
                correlation_id=actor.correlation_id,
            ),
            timestamp=int(time.time()),
        )
        headers["Content-Type"] = "application/json"

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(url, content=body, headers=headers, follow_redirects=False)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("AI-service %s unreachable: %s", path, exc)
            raise AIAssistantError("AI-service unreachable", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True) from exc
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code != 200:
            logger.warning(
                "AI-service %s answered HTTP %s: %s",
                path,
                response.status_code,
                response.text[:500],
            )
            if response.status_code in (401, 403):
                code = "AI_SERVICE_AUTH_ERROR"
            elif response.status_code >= 500:
                code = "AI_SERVICE_ERROR"
            else:
                code = "AI_SERVICE_REJECTED"
            raise AIAssistantError(
                f"AI-service answered HTTP {response.status_code}",
                error_code=code,
                unavailable=response.status_code in (502, 503, 504),
            )

        try:
            envelope = response.json()
        except ValueError as exc:
            raise _bad_response(path) from exc
        data = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(data, dict):
            raise _bad_response(path)
        return data


def _bad_response(operation: str) -> AIAssistantError:
    return AIAssistantError(
        f"AI-service returned an unreadable {operation} response",
        error_code="AI_SERVICE_BAD_RESPONSE",
    )


def _memory_items(data: dict[str, Any]) -> list[MemoryItem]:
    items = data.get("items")
    if not isinstance(items, list):
        raise _bad_response("memory")
    parsed = []
    for item in items:
        topic = item.get("topic") if isinstance(item, dict) else None
        score = item.get("mastery_score") if isinstance(item, dict) else None
        attempts = item.get("attempts") if isinstance(item, dict) else None
        if (
            not isinstance(topic, str)
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0.0 <= float(score) <= 1.0
            or isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or attempts < 0
        ):
            raise _bad_response("memory")
        parsed.append(MemoryItem(topic=topic, mastery_score=float(score), attempts=attempts))
    return parsed
