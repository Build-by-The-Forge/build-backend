"""POST /ai/tutor/turn (M3-F, R1): one question, answered on its own, nothing kept.

AI-service is replaced by the recording gateway of test_ai_api; the signed
call and every citation check are the gateway tests', and the real two-service
flow is the boundary suite's. What is tested here is the route: who may ask,
what it accepts and returns, how failures answer, and that nothing of a turn
is stored, logged or counted.
"""

import logging
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.ai import get_ai_assistant_gateway
from app.core.config import Settings, settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.domain.ai.assistant import NOT_COVERED_ANSWER, AIAssistantError, TutorAnswer, TutorCitation
from app.main import app
from tests.integration.ai.test_ai_api import RecordingGateway, gateway, member  # noqa: F401


@pytest.fixture(autouse=True)
def tutor_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_tutor_enabled", True)


CITATION_FIELDS = {"number", "source_id", "asset_id", "title", "page_start", "page_end", "excerpt"}
QUESTION = "What does the stored-question-marker-7c1e say about osmosis?"


async def test_a_student_gets_the_answer_with_its_checked_citations(client, gateway):  # noqa: F811
    user_id, tenant_id, h = await member(client, "student")

    response = client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "answer": "answer [1]",
        "grounded": True,
        "citations": [
            {
                "number": 1,
                "source_id": "source-1",
                "asset_id": "asset-1",
                "title": "Notes.pdf",
                "page_start": 3,
                "page_end": 4,
                "excerpt": "A passage.",
            }
        ],
    }
    [(name, actor, args)] = gateway.calls
    assert (name, args) == ("tutor_turn", (QUESTION,))
    assert (actor.tenant_id, actor.user_id, actor.role) == (tenant_id, user_id, "student")
    assert actor.permission == "ai.use" and actor.membership_id


async def test_a_citation_holds_exactly_the_contracts_fields_and_nothing_internal(client, gateway):  # noqa: F811
    _, _, h = await member(client, "student")

    response = client.post("/ai/tutor/turn", json={"message": "q"}, headers=h)

    data = response.json()["data"]
    assert set(data) == {"answer", "grounded", "citations"}
    assert all(set(c) == CITATION_FIELDS for c in data["citations"])
    for internal in ("chunk_id", "context", "memory", "tenant", "storage", "run_number", "attempt"):
        assert internal not in response.text


async def test_the_not_covered_reply_has_no_citations(client, gateway):  # noqa: F811
    gateway.tutor_answer = TutorAnswer(NOT_COVERED_ANSWER, False)
    _, _, h = await member(client, "student")

    response = client.post("/ai/tutor/turn", json={"message": "q"}, headers=h)

    assert response.json()["data"] == {"answer": NOT_COVERED_ANSWER, "grounded": False, "citations": []}


async def test_a_lecturer_may_ask_too(client, gateway):  # noqa: F811
    _, _, h = await member(client, "lecturer")
    assert client.post("/ai/tutor/turn", json={"message": "q"}, headers=h).status_code == 200


def test_an_unauthenticated_request_is_401(client, gateway):  # noqa: F811
    assert client.post("/ai/tutor/turn", json={"message": "q"}).status_code == 401
    assert gateway.calls == []


async def test_a_tenant_without_membership_is_refused(client, gateway):  # noqa: F811
    _, _, h = await member(client, "student")
    _, _, other = await member(client, "student")
    mixed = {**h, "X-Tenant-Slug": other["X-Tenant-Slug"]}
    assert client.post("/ai/tutor/turn", json={"message": "q"}, headers=mixed).status_code == 403
    assert gateway.calls == []


async def test_the_tenant_comes_from_the_membership_not_the_request(client, gateway):  # noqa: F811
    user_id, tenant_id, h = await member(client, "student")
    _, other_tenant_id, _ = await member(client, "student")
    spoofed = {**h, "X-Tenant-ID": other_tenant_id, "X-User-ID": str(uuid4())}

    assert client.post("/ai/tutor/turn", json={"message": "q"}, headers=spoofed).status_code == 200

    [(_, actor, _)] = gateway.calls
    assert (actor.tenant_id, actor.user_id) == (tenant_id, user_id)


@pytest.mark.parametrize(
    "extra",
    [
        {"tenant_id": "x"},
        {"user_id": "x"},
        {"membership_id": "x"},
        {"role": "x"},
        # R1 keeps no history: a client cannot send any, however it is named.
        {"earlier_questions": ["What is diffusion?"]},
        {"earlier_questions": []},
        {"history": [{"role": "assistant", "content": "a"}]},
        {"conversation_id": "c1"},
        {"idempotency_key": "k"},
        {"denied_assets": []},
    ],
)
async def test_a_body_naming_anything_but_the_message_is_422(client, gateway, extra):  # noqa: F811
    _, _, h = await member(client, "student")
    response = client.post("/ai/tutor/turn", json={"message": "hi", **extra}, headers=h)
    assert response.status_code == 422
    assert gateway.calls == []


@pytest.mark.parametrize("body", [{"message": "x" * 4001}, {"message": ""}, {}, {"message": 5}, {"message": None}])
async def test_the_message_is_bounded(client, gateway, body):  # noqa: F811
    _, _, h = await member(client, "student")
    assert client.post("/ai/tutor/turn", json=body, headers=h).status_code == 422
    assert gateway.calls == []


async def test_a_message_of_exactly_4000_characters_is_accepted(client, gateway):  # noqa: F811
    _, _, h = await member(client, "student")
    assert client.post("/ai/tutor/turn", json={"message": "x" * 4000}, headers=h).status_code == 200


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AIAssistantError("x", error_code="AI_SERVICE_ERROR"), 502, "AI_UPSTREAM_ERROR"),
        (AIAssistantError("x", error_code="AI_SERVICE_BAD_RESPONSE"), 502, "AI_UPSTREAM_ERROR"),
        (AIAssistantError("x", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True), 503, "AI_UNAVAILABLE"),
        (AIAssistantError("x", error_code="ANSWER_WITHHELD"), 503, "ANSWER_WITHHELD"),
    ],
)
async def test_failures_answer_with_the_contracts_codes_and_nothing_else(client, error, status, code):
    failing = RecordingGateway(error=error)
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: failing
    try:
        _, _, h = await member(client, "student")
        response = client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h)
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert QUESTION not in response.text
    if code == "ANSWER_WITHHELD":
        assert int(response.headers["retry-after"]) >= 1


async def test_the_turn_is_rate_limited_per_user(client, gateway):  # noqa: F811
    from app.application.identity.throttle import AI_REQUESTS_PER_USER

    _, _, h = await member(client, "student")
    for _ in range(AI_REQUESTS_PER_USER.limit):
        assert client.post("/ai/tutor/turn", json={"message": "q"}, headers=h).status_code == 200
    limited = client.post("/ai/tutor/turn", json={"message": "q"}, headers=h)
    assert limited.status_code == 429 and "retry-after" in limited.headers
    assert len(gateway.calls) == AI_REQUESTS_PER_USER.limit  # the refused turn reached no AI service

    _, _, other = await member(client, "student")
    assert client.post("/ai/tutor/turn", json={"message": "q"}, headers=other).status_code == 200


# --- Nothing of a turn is kept (R1) -------------------------------------------------------


async def row_counts() -> dict[str, int]:
    async with SessionLocal() as session:
        return {
            table.name: await session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables
        }


async def test_a_turn_stores_nothing(client, gateway):  # noqa: F811
    _, _, h = await member(client, "student")
    before = await row_counts()

    for message in (QUESTION, "another question", QUESTION):
        assert client.post("/ai/tutor/turn", json={"message": message}, headers=h).status_code == 200

    assert await row_counts() == before


async def test_a_failed_turn_stores_nothing_either(client):
    failing = RecordingGateway(error=AIAssistantError("x", error_code="ANSWER_WITHHELD"))
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: failing
    try:
        _, _, h = await member(client, "student")
        before = await row_counts()
        assert client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h).status_code == 503
        assert await row_counts() == before
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)


async def test_no_question_or_answer_reaches_a_log_a_metric_or_the_error_counters(client, gateway, caplog):  # noqa: F811
    from app.core.metrics import metrics_payload

    gateway.tutor_answer = TutorAnswer(
        "stored-answer-marker-3b9d [1]", True, (TutorCitation(1, "s", "a", "Title.pdf", 1, 1, "stored-excerpt-marker-8e2f"),)
    )
    _, _, h = await member(client, "student")

    with caplog.at_level(logging.DEBUG):
        ok = client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h)
        refused = client.post("/ai/tutor/turn", json={"message": "x" * 5000, "marker": QUESTION}, headers=h)
    metrics = metrics_payload().decode("utf-8")

    assert ok.status_code == 200 and refused.status_code == 422
    for secret in ("stored-question-marker-7c1e", "stored-answer-marker-3b9d", "stored-excerpt-marker-8e2f"):
        assert secret not in caplog.text, "a log line holds the question or the answer"
        assert secret not in metrics, "a metric holds the question or the answer"
        assert secret not in refused.text


async def test_an_unexpected_failure_reveals_and_logs_nothing_of_the_question(client, caplog):
    class Broken(RecordingGateway):
        async def tutor_turn(self, actor, message):
            # The question in the message, and again in a chained cause.
            try:
                raise ValueError(f"bad input {message}")
            except ValueError as cause:
                raise RuntimeError(f"cannot answer {message}") from cause

    app.dependency_overrides[get_ai_assistant_gateway] = lambda: Broken()
    try:
        _, _, h = await member(client, "student")
        with caplog.at_level(logging.DEBUG):
            response = client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h)
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)

    # The same answer as any AI failure, and the log names the exception's type only.
    assert response.status_code == 502 and response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"
    assert "stored-question-marker-7c1e" not in response.text
    assert "stored-question-marker-7c1e" not in caplog.text
    assert "RuntimeError" in caplog.text


# --- Off by default -----------------------------------------------------------------------


def test_the_route_is_off_unless_an_environment_turns_it_on():
    assert Settings.model_fields["ai_tutor_enabled"].default is False


async def test_while_off_the_route_does_not_exist_for_anyone_and_costs_nothing(client, gateway, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "ai_tutor_enabled", False)
    _, _, h = await member(client, "student")
    before = await row_counts()

    response = client.post("/ai/tutor/turn", json={"message": QUESTION}, headers=h)

    assert response.status_code == 404
    assert gateway.calls == []  # AI-service was not asked
    assert QUESTION not in response.text
    assert await row_counts() == before


async def test_while_off_an_unauthenticated_caller_still_gets_401_not_a_hint(client, gateway, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "ai_tutor_enabled", False)
    assert client.post("/ai/tutor/turn", json={"message": "q"}).status_code == 401
