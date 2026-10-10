import json

import httpx
import pytest
from app.domain.ai.assistant import AIActor, AIAssistantError
from app.infrastructure.ai.assistant_gateway import HttpAIAssistantGateway
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    Direction,
    ServiceKeys,
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


def gateway(handler) -> HttpAIAssistantGateway:
    return HttpAIAssistantGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        keys=KEYS,
    )


def ok(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"success": True, "data": data, "message": ""})


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
    assert json.loads(request.content) == {"message": "What is osmosis?"}
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
        bodies[request.url.path] = json.loads(request.content)
        if request.url.path.endswith("explain"):
            return ok({"explanation": "E"})
        return ok({"questions": [MCQ], "discarded": 0})

    g = gateway(handler)
    assert (await g.explain(ACTOR, "osmosis")).explanation == "E"
    generated = await g.generate_questions(ACTOR, "cells", 3, "medium", "mcq")
    assert [q.to_dict() for q in generated.questions] == [MCQ]
    assert bodies == {
        "/v1/ai/explain": {"subject": "osmosis"},
        "/v1/ai/generate-questions": {
            "topic": "cells",
            "count": 3,
            "difficulty": "medium",
            "question_type": "mcq",
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
