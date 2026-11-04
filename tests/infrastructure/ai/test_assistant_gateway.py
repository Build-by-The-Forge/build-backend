import json
import time
from dataclasses import replace

import httpx
import pytest

from app.core.config import settings
from app.domain.ai.assistant import AIActor, AIAssistantError, MemoryItem, MemoryObservation
from app.infrastructure.ai.assistant_gateway import RESPONSE_NONCE_RECEIVER, HttpAIAssistantGateway
from app.infrastructure.security.replay_store import ReplayStoreUnavailable
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    HEADER_RESPONSE_SIGNATURE,
    HEADER_RESPONSE_TIMESTAMP,
    Direction,
    ServiceKeys,
    canonical_response,
    compute_signature,
    sha256_hex,
    verify_request,
)

TENANT = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
ACTOR = AIActor(
    tenant_id=TENANT,
    user_id="0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d",
    membership_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    role="student",
    permission="ai.use",
    correlation_id="corr-7",
)
MCQ = {
    "question_type": "mcq",
    "prompt": "Which organelle makes ATP?",
    "options": [
        {"text": "Nucleus", "is_correct": False},
        {"text": "Mitochondrion", "is_correct": True},
    ],
    "explanation": "Respiration.",
    "difficulty": "medium",
}
KEYS = ServiceKeys(current="test-backend-to-ai-secret-for-assistant-tests-01")
RESPONSE_KEYS = ServiceKeys(current="test-ai-to-backend-secret-for-assistant-tests-02")
SOURCE = {"asset_id": "asset-1", "run_number": 1, "attempt": 1}


class Nonces:
    """The replay store, in memory: each nonce is accepted once."""

    def __init__(self) -> None:
        self.claimed: list[tuple[str, str, str]] = []

    async def claim(self, receiver: str, sender: str, request_id: str) -> bool:
        fresh = (receiver, sender, request_id) not in self.claimed
        self.claimed.append((receiver, sender, request_id))
        return fresh


def sign(request: httpx.Request, response: httpx.Response, *, nonce: str | None = None, request_id: str | None = None):
    """Sign a response as AI-service does: for the request's id and the nonce
    in its signed body, over the exact bytes."""
    timestamp = str(int(time.time()))
    canonical = canonical_response(
        service="ai-service",
        request_id=request_id or request.headers["x-build-request-id"],
        nonce=nonce or json.loads(request.content)["response_nonce"],
        timestamp=timestamp,
        body_sha256=sha256_hex(response.content),
    )
    headers = {
        **response.headers,
        HEADER_RESPONSE_TIMESTAMP: timestamp,
        HEADER_RESPONSE_SIGNATURE: compute_signature(RESPONSE_KEYS.current, canonical),
    }
    return httpx.Response(response.status_code, content=response.content, headers=headers)


def signing(handler):
    """AI-service's side: a retrieving call's 200 is signed for its nonce."""

    async def wrapped(request: httpx.Request) -> httpx.Response:
        response = await handler(request)
        nonce = json.loads(request.content).get("response_nonce") if request.content else None
        if response.status_code == 200 and nonce and "x-build-response-signature" not in response.headers:
            return sign(request, response)
        return response

    return wrapped


def gateway(handler, *, nonces: Nonces | None = None, denied_assets=None, signed: bool = True) -> HttpAIAssistantGateway:
    extra = {} if denied_assets is None else {"denied_assets": denied_assets}
    return HttpAIAssistantGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(signing(handler) if signed else handler)),
        keys=KEYS,
        response_keys=RESPONSE_KEYS,
        nonce_store=nonces if nonces is not None else Nonces(),
        **extra,
    )


def ok(data: dict, sources: list | None = None) -> httpx.Response:
    return httpx.Response(
        200, json={"success": True, "data": data, "message": "", "sources_used": [SOURCE] if sources is None else sources}
    )


def verified_context(request: httpx.Request) -> ServiceContext:
    return verify_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="POST",
        target=request.url.raw_path.decode(),
        headers=dict(request.headers),
        body_sha256=sha256_hex(request.content),
        now=int(request.headers["x-build-timestamp"]),
    ).context


async def test_chat_is_signed_with_only_the_checked_permission():
    seen: list[httpx.Request] = []

    async def handler(request):
        seen.append(request)
        return ok({"answer": "A", "context_used": [{"text": "c1"}], "memory_used": "m"})

    answer = await gateway(handler).chat(ACTOR, "What is osmosis?")

    assert (answer.answer, answer.context) == ("A", ["c1"])
    [request] = seen
    assert request.url.path == "/v1/ai/chat"
    body = json.loads(request.content)
    assert len(body.pop("response_nonce")) == 43  # a fresh token_urlsafe(32)
    assert body == {"message": "What is osmosis?", "denied_assets": []}
    assert "authorization" not in request.headers
    assert verified_context(request) == ServiceContext.for_user(
        tenant_id=TENANT,
        user_id=ACTOR.user_id,
        membership_id=ACTOR.membership_id,
        role="student",
        permissions=["ai.use"],
        correlation_id="corr-7",
    )


async def test_explain_and_question_bodies_name_no_identity():
    bodies: dict[str, dict] = {}

    async def handler(request):
        body = json.loads(request.content)
        assert body.pop("response_nonce")
        bodies[request.url.path] = body
        if request.url.path.endswith("explain"):
            return ok({"explanation": "E"})
        return ok({"questions": [MCQ], "discarded": 0})

    g = gateway(handler)
    assert (await g.explain(ACTOR, "osmosis")).explanation == "E"
    generated = await g.generate_questions(ACTOR, "cells", 3, "medium", "mcq")
    assert [q.to_dict() for q in generated.questions] == [MCQ]
    assert bodies == {
        "/v1/ai/explain": {"subject": "osmosis", "denied_assets": []},
        "/v1/ai/generate-questions": {
            "topic": "cells",
            "count": 3,
            "difficulty": "medium",
            "question_type": "mcq",
            "denied_assets": [],
        },
    }


@pytest.mark.parametrize(
    "status,code,unavailable",
    [
        (401, "AI_SERVICE_AUTH_ERROR", False),
        (403, "AI_SERVICE_AUTH_ERROR", False),
        (422, "AI_SERVICE_REJECTED", False),
        (500, "AI_SERVICE_ERROR", False),
        (503, "AI_SERVICE_ERROR", True),
        (307, "AI_SERVICE_REJECTED", False),
    ],
)
async def test_non_200_answers_become_gateway_errors(status, code, unavailable):
    async def handler(request):
        headers = {"location": "http://elsewhere/"} if status == 307 else {}
        return httpx.Response(status, json={"detail": "secret detail"}, headers=headers)

    with pytest.raises(AIAssistantError) as exc:
        await gateway(handler).chat(ACTOR, "hi")
    assert (exc.value.error_code, exc.value.unavailable) == (code, unavailable)
    assert "secret detail" not in str(exc.value)


async def test_an_unreachable_service_is_unavailable():
    async def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(AIAssistantError) as exc:
        await gateway(handler).explain(ACTOR, "x")
    assert (exc.value.error_code, exc.value.unavailable) == ("AI_SERVICE_UNAVAILABLE", True)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"data": []}),
        httpx.Response(200, json={"data": {"answer": 5, "context_used": []}}),
    ],
)
async def test_unreadable_answers_are_bad_responses(response):
    async def handler(request):
        return response

    with pytest.raises(AIAssistantError) as exc:
        await gateway(handler).chat(ACTOR, "hi")
    assert exc.value.error_code == "AI_SERVICE_BAD_RESPONSE"


def with_(**changes) -> dict:
    return {**MCQ, **changes}


@pytest.mark.parametrize(
    "item",
    [
        with_(options=[{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}]),
        with_(options=[{"text": "A", "is_correct": True}]),
        with_(options=[{"text": "A", "is_correct": True}, {"text": " a", "is_correct": False}]),
        with_(options=[{"text": "A", "is_correct": "yes"}, {"text": "B", "is_correct": False}]),
        with_(prompt=" "),
        with_(question_type="essay"),
        with_(difficulty="hard"),
        with_(question_type="true_false"),
        "not an object",
    ],
    ids=[
        "two-correct",
        "one-option",
        "duplicate",
        "non-bool",
        "blank-prompt",
        "unknown-type",
        "unrequested-difficulty",
        "tf-without-true-false",
        "string",
    ],
)
async def test_the_backend_rechecks_every_generated_question(item):
    async def handler(request):
        return ok({"questions": [MCQ, item], "discarded": 2})

    generated = await gateway(handler).generate_questions(ACTOR, "cells", 5, "medium", "mcq")
    assert [q.to_dict() for q in generated.questions] == [MCQ]
    assert generated.discarded == 3  # AI-service's two plus the backend's one


async def test_more_questions_than_asked_are_cut_and_counted():
    async def handler(request):
        return ok({"questions": [MCQ] * 4, "discarded": 0})

    generated = await gateway(handler).generate_questions(ACTOR, "cells", 2, "medium", "mcq")
    assert (len(generated.questions), generated.discarded) == (2, 2)


@pytest.mark.parametrize(
    "data",
    [{"questions": "Q", "discarded": 0}, {"questions": [], "discarded": -1}, {"questions": []}],
)
async def test_a_malformed_generation_answer_is_a_bad_response(data):
    async def handler(request):
        return ok(data)

    with pytest.raises(AIAssistantError) as exc:
        await gateway(handler).generate_questions(ACTOR, "cells", 2, "medium", "mcq")
    assert exc.value.error_code == "AI_SERVICE_BAD_RESPONSE"


async def test_memory_query_and_upsert_are_signed_with_the_checked_permission():
    seen: list[httpx.Request] = []

    async def handler(request):
        seen.append(request)
        return ok({"items": [{"topic": "algebra", "mastery_score": 0.6, "attempts": 1}]})

    g = gateway(handler)
    assert await g.query_memory(ACTOR, ["algebra"]) == [MemoryItem("algebra", 0.6, 1)]
    submitter = replace(ACTOR, permission="assessment.attempt.submit")
    await g.record_memory(submitter, [MemoryObservation("algebra", True)])

    query, upsert = seen
    assert (query.url.path, json.loads(query.content)) == ("/v1/ai/memory/query", {"topics": ["algebra"]})
    assert (upsert.url.path, json.loads(upsert.content)) == (
        "/v1/ai/memory/upsert",
        {"observations": [{"topic": "algebra", "correct": True}]},
    )
    assert verified_context(query).permissions == ("ai.use",)
    assert verified_context(upsert).permissions == ("assessment.attempt.submit",)


@pytest.mark.parametrize(
    "items",
    [
        "x",
        [{"topic": "a", "mastery_score": 1.5, "attempts": 1}],
        [{"topic": "a", "mastery_score": True, "attempts": 1}],
        [{"topic": "a", "mastery_score": 0.5, "attempts": -1}],
        [{"topic": 3, "mastery_score": 0.5, "attempts": 1}],
    ],
)
async def test_malformed_memory_answers_are_bad_responses(items):
    async def handler(request):
        return ok({"items": items})

    with pytest.raises(AIAssistantError) as exc:
        await gateway(handler).query_memory(ACTOR)
    assert exc.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@pytest.mark.parametrize(
    "call",
    [
        lambda g: g.query_memory(ACTOR, ["algebra"]),
        lambda g: g.record_memory(ACTOR, [MemoryObservation("algebra", True)]),
    ],
    ids=["query", "record"],
)
async def test_a_closed_gate_sends_no_memory_request(monkeypatch, call):
    monkeypatch.setattr(settings, "learning_memory_enabled", False)
    sent = []

    def handler(request):
        sent.append(request)
        return ok({"items": []})

    with pytest.raises(AIAssistantError) as refused:
        await call(gateway(handler))
    assert refused.value.error_code == "LEARNING_MEMORY_DISABLED"
    assert refused.value.unavailable is True
    assert sent == []


# --- M3-D: retrieving calls carry the denial list and a nonce, and accept only a
# signed, sourced response ---------------------------------------------------------------


async def test_each_retrieving_call_sends_the_denial_list_and_a_fresh_nonce():
    bodies: list[dict] = []

    async def handler(request):
        bodies.append(json.loads(request.content))
        return ok({"answer": "A", "context_used": [], "memory_used": ""})

    async def denied(tenant_id):
        assert tenant_id == TENANT
        return frozenset({"asset-b", "asset-a"})

    g = gateway(handler, denied_assets=denied)
    await g.chat(ACTOR, "one")
    await g.chat(ACTOR, "two")
    assert [b["denied_assets"] for b in bodies] == [["asset-a", "asset-b"]] * 2
    assert bodies[0]["response_nonce"] != bodies[1]["response_nonce"]


async def test_an_unreadable_denial_list_sends_nothing():
    sent: list[httpx.Request] = []

    async def handler(request):
        sent.append(request)
        return ok({"answer": "A", "context_used": [], "memory_used": ""})

    async def unreadable(tenant_id):
        raise RuntimeError("outbox down")

    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, denied_assets=unreadable).chat(ACTOR, "hi")
    assert raised.value.unavailable and sent == []


def answer() -> httpx.Response:
    return ok({"answer": "A", "context_used": [], "memory_used": ""})


@pytest.mark.parametrize(
    "respond",
    [
        lambda request: answer(),  # unsigned
        lambda request: httpx.Response(
            200, content=sign(request, answer()).content + b" ", headers=sign(request, answer()).headers
        ),  # body changed after signing
        lambda request: sign(request, answer(), request_id="9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"),
        lambda request: sign(request, answer(), nonce="another-nonce-0123456789abcdef"),
        lambda request: sign(
            request, httpx.Response(200, json={"success": True, "data": {"answer": "A", "context_used": [], "memory_used": ""}})
        ),
        lambda request: sign(request, ok({"answer": "A", "context_used": [], "memory_used": ""}, sources=[{"asset_id": "a"}])),
        lambda request: sign(request, ok({"answer": "A", "context_used": [], "memory_used": ""}, sources="asset-1")),
    ],
    ids=["unsigned", "body-changed", "other-request", "other-nonce", "no-sources", "malformed-source", "sources-not-a-list"],
)
async def test_a_response_that_is_not_signed_for_this_request_and_nonce_or_unsourced_is_withheld(respond):
    async def handler(request):
        return respond(request)

    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, signed=False).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE" and not raised.value.unavailable


async def test_a_response_signed_with_another_secret_is_withheld():
    async def handler(request):
        return sign(request, answer())

    other = HttpAIAssistantGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        keys=KEYS,
        response_keys=ServiceKeys(current="a-different-ai-to-backend-secret-000000000"),
        nonce_store=Nonces(),
    )
    with pytest.raises(AIAssistantError) as raised:
        await other.chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


async def test_an_accepted_response_consumes_its_nonce():
    nonces = Nonces()
    sent: list[str] = []

    async def handler(request):
        sent.append(json.loads(request.content)["response_nonce"])
        return answer()

    assert (await gateway(handler, nonces=nonces).chat(ACTOR, "hi")).answer == "A"
    assert nonces.claimed == [(RESPONSE_NONCE_RECEIVER, "ai-service", sent[0])]


async def test_a_response_for_a_consumed_nonce_is_refused_even_identical_and_signed():
    nonces = Nonces()

    async def handler(request):
        # A response for this nonce was already accepted.
        nonce = json.loads(request.content)["response_nonce"]
        nonces.claimed.append((RESPONSE_NONCE_RECEIVER, "ai-service", nonce))
        return sign(request, answer())

    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, nonces=nonces, signed=False).chat(ACTOR, "hi")
    assert raised.value.error_code == "AI_SERVICE_BAD_RESPONSE"


async def test_without_the_replay_store_the_response_is_not_accepted():
    class Down:
        async def claim(self, receiver, sender, request_id):
            raise ReplayStoreUnavailable("down")

    async def handler(request):
        return answer()

    with pytest.raises(AIAssistantError) as raised:
        await gateway(handler, nonces=Down()).chat(ACTOR, "hi")
    assert raised.value.unavailable


@pytest.mark.parametrize("size,sent_calls", [(1000, 1), (1001, 0)])
async def test_the_shared_denial_limit_is_never_exceeded(size, sent_calls):
    sent: list[dict] = []

    async def handler(request):
        sent.append(json.loads(request.content))
        return answer()

    async def denied(tenant_id):
        return frozenset(f"asset-{i}" for i in range(size))

    g = gateway(handler, denied_assets=denied)
    if sent_calls:
        await g.chat(ACTOR, "hi")
        assert len(sent[0]["denied_assets"]) == 1000
    else:
        with pytest.raises(AIAssistantError) as raised:
            await g.chat(ACTOR, "hi")
        assert raised.value.unavailable
    assert len(sent) == sent_calls  # never a truncated list
