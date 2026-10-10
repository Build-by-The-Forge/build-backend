"""Client -> backend /ai/* -> signed -> AI-service -> response (C15, C27, C29).

AI-service runs MODEL_PROVIDER=deterministic in this topology, so answers are
a fixed format naming the prompt digest; what is verified is the path and the
scoping, not tutoring quality. Retrieval context names the tenant it searched
and chat memory comes from AI-service's learning_memory table.
"""

import asyncio
import uuid

import asyncpg
import pytest

from boundary.conftest import AI_APP_DSN


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


def test_c27_chat_flows_through_both_services(backend, tenant_a):
    response = backend.post("/ai/chat", json={"message": "What is osmosis?"}, headers=tenant_a.h("student"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["answer"].startswith("[deterministic model]")
    # AI-service's retrieval ran for the member's tenant (C15).
    assert data["context"] and data["context"][0].startswith(f"Tenant {tenant_a.tenant_id} ")


def test_c27_explain_and_question_generation_flow(backend, tenant_a):
    explained = backend.post("/ai/explain", json={"subject": "osmosis"}, headers=tenant_a.h("student"))
    generated = backend.post("/ai/generate-questions", json={"topic": "cells", "count": 3}, headers=tenant_a.h("lecturer"))
    assert explained.status_code == 200, explained.text
    assert generated.status_code == 200, generated.text
    assert explained.json()["data"]["explanation"].startswith("[deterministic model]")
    assert generated.json()["data"]["questions"].startswith("[deterministic model]")


def test_c27_a_student_cannot_generate_questions(backend, tenant_a):
    response = backend.post("/ai/generate-questions", json={"topic": "cells"}, headers=tenant_a.h("student"))
    assert response.status_code == 403


def test_c15_headers_cannot_choose_another_tenant(backend, tenant_a, tenant_b):
    spoofed = {
        **tenant_a.h("student"),
        "X-Tenant-ID": tenant_b.tenant_id,
        "X-School-ID": "1",
        "X-BUILD-Context": "e30",
    }
    response = backend.post("/ai/chat", json={"message": "hello"}, headers=spoofed)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["context"][0].startswith(f"Tenant {tenant_a.tenant_id} ")


def test_c15_a_tenant_slug_without_membership_is_refused(backend, tenant_a, tenant_b):
    headers = {**tenant_a.h("student"), "X-Tenant-Slug": tenant_b.slug}
    assert backend.post("/ai/chat", json={"message": "hello"}, headers=headers).status_code == 403


@pytest.mark.parametrize("path", ["/ai/chat", "/ai/explain", "/ai/generate-questions"])
@pytest.mark.parametrize("field", ["tenant_id", "user_id"])
def test_c29_a_body_naming_an_identity_is_422_at_the_backend(backend, tenant_a, path, field):
    body = {"/ai/chat": {"message": "hi"}, "/ai/explain": {"subject": "x"}, "/ai/generate-questions": {"topic": "x"}}[path]
    response = backend.post(path, json={**body, field: str(uuid.uuid4())}, headers=tenant_a.h("lecturer"))
    assert response.status_code == 422


def test_c29_ai_service_reads_memory_only_for_the_signed_user_and_tenant(ai, tenant_a, memories):
    from boundary.conftest import jbytes, to_ai, user_context

    own, marker = memories
    student = tenant_a.members["student"]
    raw = jbytes({"message": "What do I know?"})
    context = user_context(tenant_a.tenant_id, student.user_id, ["ai.use"], membership_id=student.membership_id, role="student")
    response = ai.post("/v1/ai/chat", content=raw, headers=to_ai("POST", "/v1/ai/chat", raw, context))
    assert response.status_code == 200, response.text
    memory_used = response.json()["data"]["memory_used"]
    assert f"{own}: mastery=0.5" in memory_used
    assert f"other-tenant-{marker}" not in memory_used
    assert f"other-user-{marker}" not in memory_used
