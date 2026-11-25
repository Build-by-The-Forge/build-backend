"""Client -> backend /ai/* -> signed -> AI-service -> response (C15, C27, C29).

AI-service runs MODEL_PROVIDER=deterministic in this topology, so answers are
a fixed format naming the prompt digest; what is verified is the path and the
scoping, not tutoring quality. Retrieval context is the passages AI-service
retrieved from the durable index for the verified tenant (each tenant has
its own uploaded document, identified by a marker), and chat memory comes
from AI-service's learning_memory table.
"""

import asyncio
import uuid

import asyncpg
import pytest

from boundary.conftest import (
    AI_APP_DSN,
    assign_scope,
    create_asset,
    create_job_for,
    pdf_document,
    retrieving,
    review_for_students,
    wait_for_status,
)

# Ingestion of a one-page PDF takes seconds; the worker is shared with
# every other test, so allow for a queue.
READY_TIMEOUT = 180


@pytest.fixture(scope="module")
def documents(ai, backend, tenant_a, tenant_b) -> dict[str, str]:
    """One ready, institutional document per tenant, each with its own marker."""
    markers = {}
    for tenant in (tenant_a, tenant_b):
        marker = uuid.uuid4().hex
        asset = create_asset(backend, tenant, pdf_document(marker))
        # Institutional on both sides: the backend's review, then the AI scope.
        review_for_students(tenant, asset["id"])
        assign_scope(ai, tenant.tenant_id, asset["id"])
        job = create_job_for(backend, tenant, asset)
        final = wait_for_status(backend, tenant, job["id"], {"ready", "failed"}, timeout=READY_TIMEOUT)
        assert final["status"] == "ready", final
        markers[tenant.tenant_id] = marker
    return markers


def assert_retrieved_from(context: list[str], own: str, other: str) -> None:
    """The context is the caller tenant's own document and never the other's."""
    assert context, "no retrieval context"
    assert any(own in passage for passage in context), context
    assert not any(other in passage for passage in context), context


def retrieved_by_ai_service(ai, tenant, message: str) -> list[str]:
    """What the AI service retrieves for the tenant's student, asked directly with
    a signed call. The backend's /ai/chat no longer returns retrieved passages
    (G-18), so retrieval scoping is observed here instead."""
    from boundary.conftest import jbytes, to_ai, user_context

    student = tenant.members["student"]
    raw = jbytes(retrieving({"query": message}))
    context = user_context(tenant.tenant_id, student.user_id, ["ai.use"], membership_id=student.membership_id, role="student")
    response = ai.post("/v1/ai/retrieve", content=raw, headers=to_ai("POST", "/v1/ai/retrieve", raw, context))
    assert response.status_code == 200, response.text
    return [item["text"] for item in response.json()["data"]]


async def _seed_memory(rows: list[tuple[str, str, str]]) -> None:
    connection = await asyncpg.connect(AI_APP_DSN)
    try:
        await connection.executemany(
            "INSERT INTO learning_memory (tenant_id, user_id, topic, mastery_score, attempts, last_interaction)"
            " VALUES ($1, $2, $3, 0.5, 1, '')",
            rows,
        )
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def memories(tenant_a, tenant_b):
    """learning_memory rows for the tenant-A student, and decoys: the same
    user id under tenant B, and another tenant-A user."""
    student = tenant_a.members["student"]
    marker = uuid.uuid4().hex[:6]
    own = f"own-{marker}"
    rows = [
        (tenant_a.tenant_id, student.user_id, own),
        (tenant_b.tenant_id, student.user_id, f"other-tenant-{marker}"),
        (tenant_a.tenant_id, tenant_a.members["lecturer"].user_id, f"other-user-{marker}"),
    ]
    asyncio.run(_seed_memory(rows))
    return own, marker


def test_c27_chat_flows_through_both_services(ai, backend, tenant_a, tenant_b, documents):
    own, other = documents[tenant_a.tenant_id], documents[tenant_b.tenant_id]
    question = f"What does reference {own} say about charge?"
    response = backend.post("/ai/chat", json={"message": question}, headers=tenant_a.h("student"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["answer"].startswith("[deterministic model]")
    # The answer is all the client gets: no retrieved passage, cited or not (G-18).
    assert set(data) == {"answer"}
    # AI-service retrieves the member's own uploaded document for that question (C15).
    assert_retrieved_from(retrieved_by_ai_service(ai, tenant_a, question), own, other)


def test_c27_explain_and_question_generation_flow(backend, tenant_a):
    explained = backend.post("/ai/explain", json={"subject": "osmosis"}, headers=tenant_a.h("student"))
    generated = backend.post("/ai/generate-questions", json={"topic": "cells", "count": 3}, headers=tenant_a.h("lecturer"))
    assert explained.status_code == 200, explained.text
    assert generated.status_code == 200, generated.text
    assert explained.json()["data"]["explanation"].startswith("[deterministic model]")
    questions = generated.json()["data"]["questions"]  # structured since M5
    assert len(questions) == 3 and questions[0]["prompt"].startswith("[deterministic ")


def test_c27_a_student_cannot_generate_questions(backend, tenant_a):
    response = backend.post("/ai/generate-questions", json={"topic": "cells"}, headers=tenant_a.h("student"))
    assert response.status_code == 403


def test_c15_headers_cannot_choose_another_tenant(ai, backend, tenant_a, tenant_b, documents):
    own, other = documents[tenant_a.tenant_id], documents[tenant_b.tenant_id]
    spoofed = {
        **tenant_a.h("student"),
        "X-Tenant-ID": tenant_b.tenant_id,
        "X-School-ID": "1",
        "X-BUILD-Context": "e30",
    }
    # The question names both tenants' documents: only the member's own may come back.
    response = backend.post("/ai/chat", json={"message": f"reference {other} reference {own}"}, headers=spoofed)
    assert response.status_code == 200, response.text
    assert set(response.json()["data"]) == {"answer"}
    # The question names both tenants' documents: the AI service, asked as the
    # member the backend resolved, returns only the member's own.
    assert_retrieved_from(retrieved_by_ai_service(ai, tenant_a, f"reference {other} reference {own}"), own, other)


def test_c15_a_tenant_slug_without_membership_is_refused(backend, tenant_a, tenant_b):
    headers = {**tenant_a.h("student"), "X-Tenant-Slug": tenant_b.slug}
    assert backend.post("/ai/chat", json={"message": "hello"}, headers=headers).status_code == 403


@pytest.mark.parametrize("path", ["/ai/chat", "/ai/explain", "/ai/generate-questions"])
@pytest.mark.parametrize("field", ["tenant_id", "user_id"])
def test_c29_a_body_naming_an_identity_is_422_at_the_backend(backend, tenant_a, path, field):
    body = {"/ai/chat": {"message": "hi"}, "/ai/explain": {"subject": "x"}, "/ai/generate-questions": {"topic": "x"}}[path]
    response = backend.post(path, json={**body, field: str(uuid.uuid4())}, headers=tenant_a.h("lecturer"))
    assert response.status_code == 422


def test_c29_a_students_memory_never_reaches_the_client(backend, tenant_a, memories):
    """G-18: the AI service may use the signed user's memory in its prompt, but
    the backend returns the answer alone. Which memory it reads is proven at the
    AI service, where the signed context is the only source of user and tenant
    (tests/unit/test_signed_ai_routes.py in ai-service)."""
    own, marker = memories
    response = backend.post("/ai/chat", json={"message": "What do I know?"}, headers=tenant_a.h("student"))
    assert response.status_code == 200, response.text
    assert set(response.json()["data"]) == {"answer"}
    for leaked in (own, f"other-tenant-{marker}", f"other-user-{marker}", "mastery="):
        assert leaked not in response.text
