"""Backend AI endpoints through the application (M3-11; C15 at the backend).

AI-service is replaced by a recording gateway here; the signed request it
would send is covered by the gateway tests, and the real two-service flow
(C27) by the boundary suite.
"""

from uuid import uuid4

import pytest
from app.api.ai import get_ai_assistant_gateway
from app.application.identity.throttle import AI_QUESTION_GENERATION_PER_USER
from app.domain.ai.assistant import (
    AIActor,
    AIAssistantError,
    AIAssistantGateway,
    ChatAnswer,
    Explanation,
    GeneratedOption,
    GeneratedQuestion,
    GeneratedQuestions,
    MemoryItem,
)
from app.main import app
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


class RecordingGateway(AIAssistantGateway):
    def __init__(self, error: AIAssistantError | None = None) -> None:
        self.calls: list[tuple[str, AIActor, tuple]] = []
        self.error = error

    def _record(self, name: str, actor: AIActor, *args) -> None:
        self.calls.append((name, actor, args))
        if self.error:
            raise self.error

    async def chat(self, actor, message):
        self._record("chat", actor, message)
        return ChatAnswer(answer=f"answer to {message}", context=["ctx"])

    async def explain(self, actor, subject):
        self._record("explain", actor, subject)
        return Explanation(explanation=f"about {subject}")

    async def query_memory(self, actor, topics=None):
        self._record("query_memory", actor, topics)
        return [MemoryItem("algebra", 0.6, 2)]

    async def record_memory(self, actor, observations):
        self._record("record_memory", actor, observations)
        return [MemoryItem(o.topic, 0.6, 1) for o in observations]

    async def generate_questions(self, actor, topic, count, difficulty, question_type):
        self._record("generate_questions", actor, topic, count, difficulty, question_type)
        options = (GeneratedOption("True", True), GeneratedOption("False", False))
        question = GeneratedQuestion(question_type, f"{topic}?", options, None, difficulty)
        return GeneratedQuestions(questions=[question] * count, discarded=1)


@pytest.fixture
def gateway():
    recorder = RecordingGateway()
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_ai_assistant_gateway, None)


async def member(client, role: str) -> tuple[str, str, dict[str, str]]:
    user_id, token = await register_and_authenticate(client, f"ai-{role}-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(user_id, role)
    return user_id, tenant_id, headers(token, slug)


async def test_chat_is_forwarded_for_the_verified_member(client, gateway):
    user_id, tenant_id, h = await member(client, "student")

    response = client.post("/ai/chat", json={"message": "What is osmosis?"}, headers=h)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"answer": "answer to What is osmosis?", "context": ["ctx"]}
    [(name, actor, args)] = gateway.calls
    assert (name, args) == ("chat", ("What is osmosis?",))
    assert (actor.tenant_id, actor.user_id, actor.role) == (tenant_id, user_id, "student")
    assert actor.permission == "ai.use"
    assert actor.membership_id


async def test_explain_and_generate_questions(client, gateway):
    _, _, h = await member(client, "lecturer")

    explained = client.post("/ai/explain", json={"subject": "osmosis"}, headers=h)
    generated = client.post(
        "/ai/generate-questions",
        json={"topic": "cells", "count": 2, "difficulty": "hard", "question_type": "true_false"},
        headers=h,
    )

    assert explained.json()["data"] == {"explanation": "about osmosis"}
    question = {
        "question_type": "true_false",
        "prompt": "cells?",
        "options": [{"text": "True", "is_correct": True}, {"text": "False", "is_correct": False}],
        "explanation": None,
        "difficulty": "hard",
    }
    assert generated.json()["data"] == {"questions": [question, question], "discarded": 1}
    assert gateway.calls[-1][2] == ("cells", 2, "hard", "true_false")
    assert [(c[0], c[1].permission) for c in gateway.calls] == [
        ("explain", "ai.use"),
        ("generate_questions", "ai.questions.generate"),
    ]


async def test_a_student_cannot_generate_questions(client, gateway):
    _, _, h = await member(client, "student")
    response = client.post("/ai/generate-questions", json={"topic": "cells"}, headers=h)
    assert response.status_code == 403
    assert gateway.calls == []


@pytest.mark.parametrize("path", ["/ai/chat", "/ai/explain", "/ai/generate-questions"])
def test_unauthenticated_requests_are_401(client, gateway, path):
    assert client.post(path, json={}).status_code == 401
    assert gateway.calls == []


async def test_a_tenant_without_membership_is_refused(client, gateway):
    _, _, h = await member(client, "lecturer")
    _, other_tenant_id, other_h = await member(client, "lecturer")
    mixed = {**h, "X-Tenant-Slug": other_h["X-Tenant-Slug"]}
    assert client.post("/ai/chat", json={"message": "hi"}, headers=mixed).status_code == 403
    assert gateway.calls == []


async def test_the_tenant_comes_from_the_membership_not_the_request(client, gateway):
    user_id, tenant_id, h = await member(client, "student")
    _, other_tenant_id, _ = await member(client, "student")
    spoofed = {**h, "X-Tenant-ID": other_tenant_id, "X-User-ID": str(uuid4())}

    response = client.post("/ai/chat", json={"message": "hi"}, headers=spoofed)

    assert response.status_code == 200
    [(_, actor, _)] = gateway.calls
    assert (actor.tenant_id, actor.user_id) == (tenant_id, user_id)


@pytest.mark.parametrize("field", ["tenant_id", "user_id", "membership_id", "role"])
async def test_a_body_naming_an_identity_is_422(client, gateway, field):
    _, _, h = await member(client, "lecturer")
    response = client.post("/ai/chat", json={"message": "hi", field: "x"}, headers=h)
    assert response.status_code == 422
    assert gateway.calls == []


@pytest.mark.parametrize(
    "path,body",
    [
        ("/ai/chat", {"message": "x" * 4001}),
        ("/ai/chat", {"message": ""}),
        ("/ai/explain", {"subject": "x" * 4001}),
        ("/ai/generate-questions", {"topic": "t", "count": 51}),
        ("/ai/generate-questions", {"topic": "t", "count": 0}),
    ],
)
async def test_inputs_are_bounded(client, gateway, path, body):
    _, _, h = await member(client, "lecturer")
    assert client.post(path, json=body, headers=h).status_code == 422
    assert gateway.calls == []


async def test_question_generation_is_rate_limited_per_user(client, gateway):
    _, _, h = await member(client, "lecturer")
    for _ in range(AI_QUESTION_GENERATION_PER_USER.limit):
        assert client.post("/ai/generate-questions", json={"topic": "t"}, headers=h).status_code == 200
    limited = client.post("/ai/generate-questions", json={"topic": "t"}, headers=h)
    assert limited.status_code == 429
    assert "retry-after" in limited.headers

    _, _, other = await member(client, "lecturer")
    assert client.post("/ai/generate-questions", json={"topic": "t"}, headers=other).status_code == 200


@pytest.mark.parametrize(
    "error,status",
    [
        (AIAssistantError("down", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True), 503),
        (AIAssistantError("refused", error_code="AI_SERVICE_AUTH_ERROR"), 502),
    ],
)
async def test_ai_service_failures_are_mapped_without_detail(client, error, status):
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: RecordingGateway(error)
    try:
        _, _, h = await member(client, "student")
        response = client.post("/ai/chat", json={"message": "hi"}, headers=h)
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)
    assert response.status_code == status
    assert "AI_SERVICE" not in response.text
    assert response.json()["success"] is False


async def test_an_unverified_email_is_refused(client, gateway):
    payload = {"email": f"ai-unverified-{uuid4()}@example.com", "password": "StrongPass123!"}
    user_id = client.post("/identity/users", json=payload).json()["data"]["id"]
    token = client.post("/identity/authenticate", json=payload).json()["data"]["access_token"]
    _, slug, _, _ = await seed_tenant_context(user_id, "student")
    response = client.post("/ai/chat", json={"message": "hi"}, headers=headers(token, slug))
    assert response.status_code == 403
    assert gateway.calls == []


async def test_a_member_reads_their_own_memory(client, gateway):
    user_id, tenant_id, h = await member(client, "student")
    response = client.get("/ai/memory", params=[("topic", "algebra")], headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"items": [{"topic": "algebra", "mastery_score": 0.6, "attempts": 2}]}
    [(name, actor, args)] = gateway.calls
    assert (name, args) == ("query_memory", (["algebra"],))
    assert (actor.tenant_id, actor.user_id, actor.permission) == (tenant_id, user_id, "ai.use")


def test_memory_requires_authentication(client, gateway):
    assert client.get("/ai/memory").status_code == 401
    assert gateway.calls == []


async def test_memory_topics_are_bounded(client, gateway):
    _, _, h = await member(client, "student")
    assert client.get("/ai/memory", params=[("topic", "x" * 256)], headers=h).status_code == 422
    assert client.get("/ai/memory", params=[("topic", "t")] * 51, headers=h).status_code == 422
    assert gateway.calls == []
