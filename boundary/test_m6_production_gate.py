"""M6 production gate on the real stack (plan §22 M6, §10, §11, §12).

The deliberate-attack list from the plan, each against the running services,
plus the database checks of §10. Several attacks are also covered row by row
in the M3 suites; here they are stated once, as the plan lists them.
"""

import asyncio
import base64
import json
import os
import time
import uuid

import asyncpg
import pytest

from boundary.conftest import A2B, B2A, BACKEND_ID, canonical_json, jbytes, sign, to_ai, user_context

BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")
CHAT = "/v1/ai/chat"


def signed_chat(context, **kw):
    raw = jbytes({"message": "hello"})
    return raw, to_ai("POST", CHAT, raw, context, **kw)


# --- forged user -----------------------------------------------------------------------


def _tampered_jwt(token: str, **claims) -> str:
    header, payload, signature = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    data.update(claims)
    forged = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    return f"{header}.{forged}.{signature}"


def test_forged_user_token_is_refused(backend, tenant_a, tenant_b):
    student = tenant_a.members["student"]
    forged = _tampered_jwt(student.token, sub=tenant_b.owner.user_id)
    headers = {"Authorization": f"Bearer {forged}", "X-Tenant-Slug": tenant_a.slug}
    assert backend.post("/ai/chat", json={"message": "hi"}, headers=headers).status_code == 401


def test_a_token_signed_with_another_key_is_refused(backend, tenant_a):
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT","kid":"primary"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": str(uuid.uuid4())}).encode()).rstrip(b"=").decode()
    token = f"{header}.{payload}.{base64.urlsafe_b64encode(b'x' * 32).rstrip(b'=').decode()}"
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_a.slug}
    assert backend.post("/ai/chat", json={"message": "hi"}, headers=headers).status_code == 401


# --- forged tenant and role ------------------------------------------------------------


def test_forged_tenant_header_without_membership_is_refused(backend, tenant_a, tenant_b):
    headers = {**tenant_a.h("student"), "X-Tenant-Slug": tenant_b.slug}
    assert backend.post("/ai/chat", json={"message": "hi"}, headers=headers).status_code == 403


def test_forged_role_header_grants_nothing(backend, tenant_a):
    headers = {**tenant_a.h("student"), "X-Role": "owner", "X-Membership-Role": "owner"}
    response = backend.post("/ai/generate-questions", json={"topic": "t"}, headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize("field,value", [("tenant_id", str(uuid.uuid4())), ("role", "owner"), ("user_id", str(uuid.uuid4()))])
def test_forged_signed_context_is_refused(ai, field, value):
    raw, headers = signed_chat(user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"], role="student"))
    context = json.loads(base64.urlsafe_b64decode(headers["X-BUILD-Context"] + "=="))
    context[field] = value
    headers["X-BUILD-Context"] = base64.urlsafe_b64encode(canonical_json(context)).rstrip(b"=").decode()
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 401


# --- forged signature, expiry, replay, wrong secret ---------------------------------------


def test_forged_signature_is_refused(ai):
    raw, headers = signed_chat(user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]))
    headers["X-BUILD-Signature"] = "v1=" + "0" * 64
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 401


def test_expired_timestamp_is_refused(ai):
    raw, headers = signed_chat(user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]), timestamp=int(time.time()) - 600)
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 401


def test_replayed_request_is_refused(ai):
    raw, headers = signed_chat(user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]))
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 200
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 401


@pytest.mark.parametrize("secret", [A2B, "build-internal-service-secret", "x" * 48])
def test_wrong_service_secret_is_refused(ai, secret):
    raw = jbytes({"message": "hello"})
    headers = sign(
        sender=BACKEND_ID,
        secret=secret,
        method="POST",
        target=CHAT,
        body=raw,
        context=user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]),
    )
    assert secret != B2A
    assert ai.post(CHAT, content=raw, headers=headers).status_code == 401


# --- cross-tenant memory -------------------------------------------------------------------


def test_cross_tenant_memory_is_invisible(ai):
    user, tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    topic = f"secret-{uuid.uuid4().hex[:6]}"
    raw = jbytes({"observations": [{"topic": topic, "correct": True}]})
    upsert = "/v1/ai/memory/upsert"
    written = ai.post(
        upsert, content=raw, headers=to_ai("POST", upsert, raw, user_context(tenant_b, user, ["assessment.attempt.submit"]))
    )
    assert written.status_code == 200, written.text

    query = "/v1/ai/memory/query"
    raw = jbytes({"topics": [topic]})
    same_user_other_tenant = ai.post(
        query, content=raw, headers=to_ai("POST", query, raw, user_context(tenant_a, user, ["ai.use"]))
    )
    assert same_user_other_tenant.json()["data"]["items"] == []


# --- unauthenticated AI request, direct AI login ----------------------------------------


def test_unauthenticated_ai_requests_are_refused(backend, ai):
    assert backend.post("/ai/chat", json={"message": "hi"}).status_code == 401
    assert ai.post(CHAT, json={"message": "hi"}).status_code == 401


@pytest.mark.parametrize("path", ["/auth/login", "/api/v1/auth/login", "/login"])
def test_there_is_no_direct_ai_login(ai, path):
    assert ai.post(path, json={"email": "a@b.c", "password": "x"}).status_code == 404


# --- rate limiting and request limits are operational -------------------------------------


def test_repeated_failed_sign_ins_are_locked(backend, tenant_a):
    email = tenant_a.members["lecturer"].email
    statuses = [
        backend.post("/identity/authenticate", json={"email": email, "password": "wrong-password-1"}).status_code
        for _ in range(7)
    ]
    assert statuses[0] == 401
    assert 429 in statuses


def test_oversized_bodies_are_refused_on_both_services(backend, ai, tenant_a):
    big = b'{"message": "' + b"x" * (1024 * 1024 + 10) + b'"}'
    assert (
        backend.post("/ai/chat", content=big, headers={**tenant_a.h("student"), "Content-Type": "application/json"}).status_code
        == 413
    )
    headers = to_ai("POST", CHAT, big, user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]))
    assert ai.post(CHAT, content=big, headers=headers).status_code == 413


def test_the_correlation_id_reaches_ai_service(ai):
    raw, headers = signed_chat(user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"]))
    response = ai.post(CHAT, content=raw, headers=headers)
    assert response.headers["x-correlation-id"] == "boundary"


# --- §10 database ----------------------------------------------------------------------------


def _fetch(sql: str):
    async def go():
        connection = await asyncpg.connect(BACKEND_APP_DSN)
        try:
            return await connection.fetch(sql)
        finally:
            await connection.close()

    return asyncio.run(go())


def _owners() -> dict[str, str]:
    rows = _fetch("SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public'")
    return {r["tablename"]: r["tableowner"] for r in rows}


def test_both_migration_version_tables_coexist_with_their_owners():
    owners = _owners()
    assert owners["alembic_version"] == "build_backend_owner"
    assert owners["ai_service_alembic_version"] == "build_ai_owner"


def test_no_legacy_ai_tables_exist():
    owners = _owners()
    assert not {"schools", "exams", "exam_sessions", "answer_sheets"} & set(owners)


def test_every_table_belongs_to_exactly_one_service():
    owners = _owners()
    ai_tables = {t for t, o in owners.items() if o == "build_ai_owner"}
    assert ai_tables == {
        "document_chunks",
        "learning_memory",
        "session_memory",
        "ai_service_alembic_version",
    }
    assert {o for t, o in owners.items() if t not in ai_tables} == {"build_backend_owner"}
    assert owners["users"] == owners["tenants"] == owners["memberships"] == "build_backend_owner"


def test_public_cannot_create_in_the_shared_schema():
    [row] = _fetch("SELECT has_schema_privilege('public', 'public', 'CREATE') AS can_create")
    assert row["can_create"] is False
