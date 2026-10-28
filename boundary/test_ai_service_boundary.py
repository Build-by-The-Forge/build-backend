"""Backend -> AI-service requests against the real AI-service.

C2-C10 (protocol), C12 (no Bearer), C13 (user routes closed), C14 (context
narrows), C29 (body cannot name an identity) at AI-service.
"""

import base64
import json
import time
import uuid

import pytest

from boundary.conftest import (
    A2B,
    AI_ID,
    B2A,
    BACKEND_ID,
    canonical_json,
    jbytes,
    sign,
    system_context,
    to_ai,
    user_context,
)

TENANT = str(uuid.uuid4())
USER = str(uuid.uuid4())
CHAT = "/v1/ai/chat"
DISPATCH = "/v1/ingest/dispatch"

AI_ROUTES = [
    ("/v1/ai/chat", "ai.use", {"message": "What is osmosis?"}),
    ("/v1/ai/explain", "ai.use", {"subject": "osmosis"}),
    ("/v1/ai/generate-questions", "ai.questions.generate", {"topic": "cells", "count": 2}),
    ("/v1/ai/retrieve", "ai.use", {"query": "osmosis"}),
    ("/v1/ai/tree/generate", "ai.use", {"course_title": "Biology", "topics": ["Cells"]}),
    ("/v1/ai/read/start", "ai.use", {"root": {"id": "c", "title": "C", "level": 0}}),
]
IDS = [r[0] for r in AI_ROUTES]


def dispatch_body(**extra) -> dict:
    job = f"bnd-job-{uuid.uuid4().hex[:12]}"
    return {
        "job_id": job,
        "asset_id": "asset-1",
        "source_id": "source-1",
        "run_number": 1,
        "attempt_count": 1,
        "idempotency_key": f"{job}-r1-a1",
        "mime_type": "application/pdf",
        "content_sha256": "ab" * 32,
        "storage_uri": "s3://build-assets/boundary.pdf",
        "correlation_id": "boundary",
        **extra,
    }


def chat_call(**kw):
    body = jbytes({"message": "hello"})
    ctx = user_context(TENANT, USER, ["ai.use"])
    return body, to_ai("POST", CHAT, body, ctx, **kw)


# --- C2: authentic requests are accepted ------------------------------------------------


@pytest.mark.parametrize("path,permission,body", AI_ROUTES, ids=IDS)
def test_c2_a_valid_signed_request_is_served(ai, path, permission, body):
    raw = jbytes(body)
    response = ai.post(path, content=raw, headers=to_ai("POST", path, raw, user_context(TENANT, USER, [permission])))
    assert response.status_code == 200, response.text


def test_c2_a_valid_signed_dispatch_is_accepted(ai):
    raw = jbytes(dispatch_body())
    headers = to_ai("POST", DISPATCH, raw, user_context(TENANT, USER, ["content.job.manage"]))
    response = ai.post(DISPATCH, content=raw, headers=headers)
    assert response.status_code == 202, response.text


# --- C3-C10: nothing signed can be changed, and nothing unsigned is trusted -------------


def test_c3_a_body_changed_after_signing_is_401(ai):
    body, headers = chat_call()
    assert ai.post(CHAT, content=body.replace(b"hello", b"hellp"), headers=headers).status_code == 401


@pytest.mark.parametrize(
    "field,value",
    [("tenant_id", str(uuid.uuid4())), ("user_id", str(uuid.uuid4())), ("permissions", ["ai.questions.generate", "ai.use"])],
)
def test_c4_a_context_changed_after_signing_is_401(ai, field, value):
    body, headers = chat_call()
    context = json.loads(base64.urlsafe_b64decode(headers["X-BUILD-Context"] + "=="))
    context[field] = value
    headers["X-BUILD-Context"] = base64.urlsafe_b64encode(canonical_json(context)).rstrip(b"=").decode()
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c5_a_query_added_after_signing_is_401(ai):
    body, headers = chat_call()
    assert ai.post(CHAT + "?tenant_id=x", content=body, headers=headers).status_code == 401


def test_c5_a_signed_query_must_match(ai):
    body = jbytes({"message": "hello"})
    headers = to_ai("POST", CHAT + "?lang=en", body, user_context(TENANT, USER, ["ai.use"]))
    assert ai.post(CHAT + "?lang=EN", content=body, headers=headers).status_code == 401


def test_c6_a_request_claiming_to_come_from_ai_service_is_401(ai):
    body = jbytes({"message": "hello"})
    headers = sign(
        sender=AI_ID, secret=B2A, method="POST", target=CHAT, body=body, context=user_context(TENANT, USER, ["ai.use"])
    )
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c7_a_request_signed_with_the_other_directions_secret_is_401(ai):
    body = jbytes({"message": "hello"})
    headers = sign(
        sender=BACKEND_ID, secret=A2B, method="POST", target=CHAT, body=body, context=user_context(TENANT, USER, ["ai.use"])
    )
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


@pytest.mark.parametrize("skew", [-61, 61, -3600])
def test_c8_a_timestamp_outside_the_window_is_401(ai, skew):
    body, headers = chat_call(timestamp=int(time.time()) + skew)
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c9_a_replayed_request_is_401(ai):
    body, headers = chat_call()
    assert ai.post(CHAT, content=body, headers=headers).status_code == 200
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


@pytest.mark.parametrize(
    "header",
    ["X-BUILD-Service", "X-BUILD-Timestamp", "X-BUILD-Request-ID", "X-BUILD-Context", "X-BUILD-Signature"],
)
def test_c10_each_missing_header_is_401(ai, header):
    body, headers = chat_call()
    del headers[header]
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c10_a_request_id_that_is_not_a_uuid4_is_401(ai):
    body, headers = chat_call(request_id="not-a-uuid")
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c10_a_context_that_is_not_base64url_is_401(ai):
    body, headers = chat_call()
    headers["X-BUILD-Context"] = headers["X-BUILD-Context"] + "*"
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def signed_with_raw_context(raw: bytes) -> tuple[bytes, dict[str, str]]:
    body = jbytes({"message": "hello"})
    return body, sign(sender=BACKEND_ID, secret=B2A, method="POST", target=CHAT, body=body, context_raw=raw)


def test_c10_a_validly_signed_non_canonical_context_is_401(ai):
    pretty = json.dumps(user_context(TENANT, USER, ["ai.use"]), indent=1).encode()
    body, headers = signed_with_raw_context(pretty)
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


def test_c10_a_validly_signed_context_with_an_unknown_field_is_401(ai):
    context = {**user_context(TENANT, USER, ["ai.use"]), "is_admin": True}
    body, headers = signed_with_raw_context(canonical_json(context))
    assert ai.post(CHAT, content=body, headers=headers).status_code == 401


# --- C12, C13: no static Bearer, no client access ----------------------------------------


@pytest.mark.parametrize("path,permission,body", AI_ROUTES, ids=IDS)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer build-ai-dev-secret-key"},
        {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln"},
        {"X-School-ID": "1"},
    ],
    ids=["no-auth", "static-bearer", "end-user-jwt", "x-school-id"],
)
def test_c12_c13_unsigned_requests_to_ai_routes_are_401(ai, path, permission, body, headers):
    response = ai.post(path, json=body, headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("path", [DISPATCH, "/v1/ingest/tasks/task_x"])
def test_c12_bearer_on_ingestion_routes_is_401(ai, path):
    method = ai.post if path == DISPATCH else ai.get
    kwargs = {"json": dispatch_body()} if path == DISPATCH else {}
    assert method(path, headers={"Authorization": f"Bearer {B2A}"}, **kwargs).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/auth/login"),
        ("GET", "/exams/"),
        ("POST", "/api/v1/exams/"),
        ("POST", "/api/v1/ai/exam/start"),
        ("POST", "/api/v1/ai/chat"),
        ("POST", "/api/v1/ingest/dispatch"),
    ],
)
def test_c13_legacy_and_old_routes_are_absent(ai, method, path):
    assert ai.request(method, path, json={}, headers={"X-School-ID": "1"}).status_code in (404, 405)


# --- C14: the context narrows only ---------------------------------------------------


@pytest.mark.parametrize("path,permission,body", AI_ROUTES, ids=IDS)
def test_c14_a_context_without_the_route_permission_is_403(ai, path, permission, body):
    other = "ai.use" if permission == "ai.questions.generate" else "ai.questions.generate"
    raw = jbytes(body)
    headers = to_ai("POST", path, raw, user_context(TENANT, USER, [other, "content.job.manage"]))
    assert ai.post(path, content=raw, headers=headers).status_code == 403


def test_c14_dispatch_without_its_permission_is_403(ai):
    raw = jbytes(dispatch_body())
    headers = to_ai("POST", DISPATCH, raw, user_context(TENANT, USER, ["ai.use"]))
    assert ai.post(DISPATCH, content=raw, headers=headers).status_code == 403


@pytest.mark.parametrize("path,permission,body", AI_ROUTES, ids=IDS)
def test_c14_a_system_context_cannot_act_as_a_user(ai, path, permission, body):
    """P3-6 §9: the worker's system context reaches no AI route."""
    raw = jbytes(body)
    assert ai.post(path, content=raw, headers=to_ai("POST", path, raw, system_context(TENANT))).status_code == 403


def test_p36_the_workers_system_context_dispatches_for_its_tenant_only(ai):
    """P3-6 §9: the backend worker's system context may dispatch; the task
    belongs to the context's tenant, and another tenant cannot see it."""
    raw = jbytes(dispatch_body())
    response = ai.post(DISPATCH, content=raw, headers=to_ai("POST", DISPATCH, raw, system_context(TENANT)))
    assert response.status_code == 202, response.text
    task = response.json()["external_task_id"]
    path = f"/v1/ingest/tasks/{task}"
    own = ai.get(path, headers=to_ai("GET", path, b"", system_context(TENANT)))
    assert own.status_code == 200 and own.json()["job_id"] == json.loads(raw)["job_id"]
    other = ai.get(path, headers=to_ai("GET", path, b"", system_context(str(uuid.uuid4()))))
    assert other.status_code == 404


# --- C29 (AI-service side): the body cannot name an identity ---------------------------


@pytest.mark.parametrize("field", ["tenant_id", "user_id"])
@pytest.mark.parametrize("path,permission,body", AI_ROUTES, ids=IDS)
def test_c29_a_signed_body_naming_an_identity_is_422(ai, path, permission, body, field):
    raw = jbytes({**body, field: str(uuid.uuid4())})
    headers = to_ai("POST", path, raw, user_context(TENANT, USER, [permission]))
    assert ai.post(path, content=raw, headers=headers).status_code == 422


@pytest.mark.parametrize("field", ["tenant_id", "user_id", "callback_url"])
def test_c18_c29_a_dispatch_body_naming_a_tenant_user_or_callback_is_422(ai, field):
    raw = jbytes(dispatch_body(**{field: "http://attacker.example/cb"}))
    headers = to_ai("POST", DISPATCH, raw, user_context(TENANT, USER, ["content.job.manage"]))
    assert ai.post(DISPATCH, content=raw, headers=headers).status_code == 422
