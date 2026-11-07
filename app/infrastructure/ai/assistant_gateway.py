"""Signed calls to AI-service's /v1/ai routes (design B.4, B.5).

Each request is signed with BUILD Service Signature v1 and a user context
carrying exactly the permission the backend checked. The body has no
identity fields. Redirects are never followed. AI-service's error detail is
logged, never returned to the client.

Retrieving calls (chat, explain, question generation) follow M3-D:

- the body carries ``denied_assets``, the documents the backend has lowered
  and AI-service hasn't acknowledged, and a fresh single-use
  ``response_nonce``;
- the response is accepted only if AI-service signed it for this request
  and nonce, over the exact bytes received, within the window; the nonce
  is then consumed in the replay store, so a second response for it is
  refused;
- it must carry ``sources_used``, and every source must be readable by the
  caller under the one read policy at that moment and not denied, checked
  after the response arrives. Otherwise the whole answer is withheld
  (``ANSWER_WITHHELD``) and nothing of it is returned.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.metrics import learning_memory_refusals_total
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
from app.infrastructure.security.replay_store import ReplayStoreUnavailable
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    HEADER_REQUEST_ID,
    Direction,
    ServiceAuthError,
    ServiceKeys,
    sign_request,
    verify_response,
)

logger = logging.getLogger(__name__)

# Consumed response nonces share the request replay store, in their own namespace.
RESPONSE_NONCE_RECEIVER = "build-backend:response"
# The most denied assets one call may carry. A contract limit shared with
# AI-service, which refuses a longer list: a change moves in both repositories,
# tested together. Past it, the tenant's retrieving calls are refused, never
# sent with part of the list.
MAX_DENIED_ASSETS = 1000


class NonceStore(Protocol):
    async def claim(self, receiver: str, sender: str, request_id: str) -> bool: ...


async def no_source_is_readable(actor: AIActor, asset_ids: set[str]) -> set[str]:
    """The fail-closed default: without the read policy wired in, no source
    passes, so no answer that used one is returned."""
    return set()


async def nothing_lowered_yet(tenant_id: str) -> frozenset[str]:
    """The constructor's default for tests and unwired gateways. The routes
    pass app.api.ai.pending_lowerings, the outbox's pending lowerings for
    the tenant (M3-D PR 5)."""
    return frozenset()


class HttpAIAssistantGateway(AIAssistantGateway):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
        keys: ServiceKeys | None = None,
        response_keys: ServiceKeys | None = None,
        nonce_store: NonceStore | None = None,
        denied_assets: Callable[[str], Awaitable[frozenset[str]]] = nothing_lowered_yet,
        readable_sources: Callable[[AIActor, set[str]], Awaitable[set[str]]] = no_source_is_readable,
    ) -> None:
        self._base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._timeout = float(timeout_seconds or settings.ai_service_timeout_seconds)
        self._client = client
        self._keys_override = keys
        self._response_keys_override = response_keys
        self._nonce_store = nonce_store
        self._denied_assets = denied_assets
        self._readable_sources = readable_sources

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

    def _response_keys(self) -> ServiceKeys:
        if self._response_keys_override is not None:
            return self._response_keys_override
        secrets_ = settings.ai_to_backend_verification_secrets
        if not secrets_:
            raise AIAssistantError(
                "AI_TO_BACKEND_SECRET is not configured",
                error_code="AI_SERVICE_NOT_CONFIGURED",
                unavailable=True,
            )
        return ServiceKeys(current=secrets_[0], previous=secrets_[1] if len(secrets_) > 1 else None)

    async def chat(self, actor: AIActor, message: str) -> ChatAnswer:
        data = await self._post_retrieving("/v1/ai/chat", {"message": message}, actor)
        answer = data.get("answer")
        context = data.get("context_used", [])
        if not isinstance(answer, str) or not isinstance(context, list):
            raise _bad_response("chat")
        texts = [item["text"] for item in context if isinstance(item, dict) and isinstance(item.get("text"), str)]
        return ChatAnswer(answer=answer, context=texts)

    async def explain(self, actor: AIActor, subject: str) -> Explanation:
        data = await self._post_retrieving("/v1/ai/explain", {"subject": subject}, actor)
        explanation = data.get("explanation")
        if not isinstance(explanation, str):
            raise _bad_response("explain")
        return Explanation(explanation=explanation)

    async def generate_questions(
        self, actor: AIActor, topic: str, count: int, difficulty: str, question_type: str
    ) -> GeneratedQuestions:
        data = await self._post_retrieving(
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
        _require_gate_open("read")
        payload: dict[str, Any] = {} if topics is None else {"topics": topics}
        return _memory_items(await self._post_data("/v1/ai/memory/query", payload, actor))

    async def record_memory(self, actor: AIActor, observations: list[MemoryObservation]) -> list[MemoryItem]:
        _require_gate_open("write")
        payload = {"observations": [{"topic": o.topic, "correct": o.correct} for o in observations]}
        return _memory_items(await self._post_data("/v1/ai/memory/upsert", payload, actor))

    async def _post_data(self, path: str, payload: dict[str, Any], actor: AIActor) -> dict[str, Any]:
        response, _ = await self._post(path, payload, actor)
        return _data_of(_envelope(response, path), path)

    async def _post_retrieving(self, path: str, payload: dict[str, Any], actor: AIActor) -> dict[str, Any]:
        try:
            denied = await self._denied_assets(actor.tenant_id)
        except Exception as exc:
            # No list, no call: absence never means none.
            logger.warning("denied assets unreadable for %s: %s", path, type(exc).__name__)
            raise AIAssistantError("denied assets unavailable", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True) from exc
        if len(denied) > MAX_DENIED_ASSETS:
            logger.error(
                "denied assets for tenant %s exceed the shared limit (%s > %s): retrieving calls refused",
                actor.tenant_id,
                len(denied),
                MAX_DENIED_ASSETS,
            )
            raise AIAssistantError("too many denied assets", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True)
        nonce = secrets.token_urlsafe(32)
        payload = {**payload, "denied_assets": sorted(denied), "response_nonce": nonce}
        response, request_id = await self._post(path, payload, actor)
        try:
            verify_response(
                direction=Direction.AI_TO_BACKEND,
                keys=self._response_keys(),
                request_id=request_id,
                nonce=nonce,
                headers=response.headers,
                body=response.content,
                now=int(time.time()),
            )
        except ServiceAuthError as exc:
            logger.warning("AI-service %s response withheld: %s", path, exc.reason)
            raise _bad_response(path) from exc
        await self._consume(nonce, path)
        envelope = _envelope(response, path)
        sources = envelope.get("sources_used")
        if not _valid_sources(sources):
            logger.warning("AI-service %s response withheld: no valid sources_used", path)
            raise _bad_response(path)
        await self._check_provenance(path, actor, {source["asset_id"] for source in sources})
        return _data_of(envelope, path)

    async def _check_provenance(self, path: str, actor: AIActor, asset_ids: set[str]) -> None:
        """Every source readable by this caller now, by the one read policy,
        and not denied now: the denial list is read again, since a document
        may have been lowered while the call was out. Any failure, or a check
        that can't run, withholds the whole answer."""
        if not asset_ids:
            return
        try:
            readable = await self._readable_sources(actor, set(asset_ids))
            denied = await self._denied_assets(actor.tenant_id)
        except Exception as exc:
            logger.warning("AI-service %s answer withheld: provenance check failed (%s)", path, type(exc).__name__)
            raise _withheld() from exc
        refused = sorted((asset_ids - readable) | (asset_ids & denied))
        if refused:
            # IDs only: never the passage, the question or the answer.
            logger.warning(
                "AI-service %s answer withheld: tenant %s user %s sources %s",
                path,
                actor.tenant_id,
                actor.user_id,
                refused,
            )
            raise _withheld()

    async def _consume(self, nonce: str, path: str) -> None:
        """Accept one response per nonce, once."""
        store = self._nonce_store
        if store is None:
            raise AIAssistantError(
                "no replay store for response nonces", error_code="AI_SERVICE_NOT_CONFIGURED", unavailable=True
            )
        try:
            fresh = await store.claim(RESPONSE_NONCE_RECEIVER, Direction.AI_TO_BACKEND.sender, nonce)
        except ReplayStoreUnavailable as exc:
            raise AIAssistantError("replay store unavailable", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True) from exc
        if not fresh:
            logger.warning("AI-service %s response withheld: nonce already used", path)
            raise _bad_response(path)

    async def _post(self, path: str, payload: dict[str, Any], actor: AIActor) -> tuple[httpx.Response, str]:
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
        request_id = headers[HEADER_REQUEST_ID]

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

        return response, request_id


def _envelope(response: httpx.Response, path: str) -> dict[str, Any]:
    try:
        envelope = response.json()
    except ValueError as exc:
        raise _bad_response(path) from exc
    if not isinstance(envelope, dict):
        raise _bad_response(path)
    return envelope


def _data_of(envelope: dict[str, Any], path: str) -> dict[str, Any]:
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise _bad_response(path)
    return data


def _valid_sources(sources: Any) -> bool:
    """sources_used is required: a list of (asset, run, attempt). Each
    source is then checked against the read policy (_check_provenance)."""
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("asset_id"), str):
            return False
        for key in ("run_number", "attempt"):
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return False
    return True


def _withheld() -> AIAssistantError:
    return AIAssistantError("the answer drew on a source the caller may not read", error_code="ANSWER_WITHHELD")


def _bad_response(operation: str) -> AIAssistantError:
    return AIAssistantError(
        f"AI-service returned an unreadable {operation} response",
        error_code="AI_SERVICE_BAD_RESPONSE",
    )


def _require_gate_open(operation: str) -> None:
    # The last point before a request leaves: every memory call passes here.
    if not settings.learning_memory_allowed:
        learning_memory_refusals_total.labels(operation=operation).inc()
        raise AIAssistantError(
            "learning memory is disabled by the production gate",
            error_code="LEARNING_MEMORY_DISABLED",
            unavailable=True,
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
