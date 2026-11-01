"""One error shape with stable codes (M3-A): what a client branches on, and what
it must never be told."""

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.api import identity
from app.api.catalogue import courses
from app.core.exceptions import AppError, code_for_status, public_message, unhandled_exception_handler
from app.core.middleware import UnhandledErrorMiddleware
from app.main import add_response_middleware, app
from tests.integration.assessment.test_assessment_visibility import assessment_with_question
from tests.integration.assessment.test_attempt_deadline import started_attempt
from tests.integration.assessment.test_question_api import register_and_authenticate

INTERNAL = "postgresql://internal-host/secret-detail"


def assert_error(response, status_code, code):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta"}
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == code
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["meta"]["request_id"] == response.headers["x-request-id"]


# --- request IDs (G-22) ---------------------------------------------------------------


@pytest.mark.parametrize("unsafe", ["x" * 129, "has space", "new\tline", "semi;colon", "<script>"])
def test_an_unsafe_request_id_is_replaced(client, unsafe):
    returned = client.get("/health/live", headers={"X-Request-ID": unsafe}).headers["x-request-id"]
    assert returned != unsafe
    assert 1 <= len(returned) <= 128


@pytest.mark.parametrize("safe", ["abc", "A.b_c:d-1", "x" * 128])
def test_a_safe_request_id_comes_back_in_the_header_and_the_body(client, safe):
    response = client.get("/identity/me", headers={"X-Request-ID": safe})
    assert response.headers["x-request-id"] == safe
    assert response.json()["meta"]["request_id"] == safe


def test_a_request_id_is_generated_when_none_is_sent(client):
    assert client.get("/health/live").headers["x-request-id"]


# --- unexpected failures (G-08) ----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unexpected_failure_on_the_course_list_reveals_nothing(client, monkeypatch):
    _, student, _, _ = await assessment_with_question(client, published=True)

    async def broken(**_):
        raise RuntimeError(INTERNAL)

    monkeypatch.setattr(courses.service, "list_courses", broken)
    response = client.get("/catalogue/courses/", headers=student)
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "secret-detail" not in response.text
    assert "RuntimeError" not in response.text


# --- stable codes ------------------------------------------------------------------------


def test_no_token_is_auth_token_invalid(client):
    response = client.get("/identity/me")
    assert_error(response, 401, "AUTH_TOKEN_INVALID")
    assert response.headers["www-authenticate"] == "Bearer"


def test_wrong_credentials_and_an_unknown_account_are_one_answer(client):
    response = client.post(
        "/identity/authenticate", json={"email": f"nobody-{uuid4()}@example.com", "password": "not-the-password-1"}
    )
    assert_error(response, 401, "AUTH_INVALID_CREDENTIALS")


def test_a_bad_refresh_token_is_auth_refresh_invalid(client):
    assert_error(client.post("/identity/refresh", json={"refresh_token": "nope"}), 401, "AUTH_REFRESH_INVALID")


@pytest.mark.asyncio
async def test_a_tenant_route_without_a_tenant_is_tenant_required(client):
    _, token = await register_and_authenticate(client, f"env-{uuid4()}@example.com")
    response = client.get("/catalogue/courses/", headers={"Authorization": f"Bearer {token}"})
    assert_error(response, 400, "TENANT_REQUIRED")


@pytest.mark.asyncio
async def test_another_tenant_is_tenant_access_denied(client):
    _, token = await register_and_authenticate(client, f"env-{uuid4()}@example.com")
    response = client.get(
        "/catalogue/courses/", headers={"Authorization": f"Bearer {token}", "X-Tenant-Slug": f"none-{uuid4().hex}"}
    )
    assert_error(response, 403, "TENANT_ACCESS_DENIED")


@pytest.mark.asyncio
async def test_a_missing_asset_is_resource_not_found(client):
    _, student, _, _ = await assessment_with_question(client, published=True)
    assert_error(client.get(f"/content/assets/{uuid4()}", headers=student), 404, "RESOURCE_NOT_FOUND")


def test_an_unknown_route_is_resource_not_found(client):
    assert_error(client.get(f"/no-such-route-{uuid4().hex}"), 404, "RESOURCE_NOT_FOUND")


def test_a_wrong_method_is_method_not_allowed(client):
    response = client.delete("/identity/authenticate")
    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert "allow" in response.headers


def test_validation_names_each_field_and_never_the_value(client):
    response = client.post("/identity/users", json={"email": "a@example.com", "password": ["never-echo-this"]})
    assert_error(response, 422, "VALIDATION_FAILED")
    fields = response.json()["error"]["details"]["fields"]
    assert fields and all(set(f) == {"field", "code", "message"} for f in fields)
    assert "never-echo-this" not in response.text


@pytest.mark.parametrize(
    "status_code,code",
    [
        (400, "BAD_REQUEST"),
        (401, "AUTH_TOKEN_INVALID"),
        (403, "PERMISSION_DENIED"),
        (404, "RESOURCE_NOT_FOUND"),
        (405, "METHOD_NOT_ALLOWED"),
        (409, "CONFLICT"),
        (422, "VALIDATION_FAILED"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_ERROR"),
        (503, "SERVICE_UNAVAILABLE"),
        (418, "BAD_REQUEST"),
        (504, "INTERNAL_ERROR"),
    ],
)
def test_each_status_has_its_default_code(status_code, code):
    assert code_for_status(status_code) == code


def test_a_named_code_wins_over_the_status_default():
    assert AppError("x", status_code=409, code="ATTEMPT_EXPIRED").code == "ATTEMPT_EXPIRED"


@pytest.mark.asyncio
async def test_a_draft_cannot_be_started_and_that_is_conflict(client):
    _, student, draft_id, _ = await assessment_with_question(client, published=False)
    response = client.post(f"/assessment/assessments/{draft_id}/attempts", headers=student)
    assert_error(response, 409, "CONFLICT")


def test_an_unavailable_dependency_is_service_unavailable(client, monkeypatch):
    async def down(_ip):
        raise AppError("service temporarily unavailable", status_code=503)

    monkeypatch.setattr(identity.throttle, "register", down)
    response = client.post("/identity/users", json={"email": f"x-{uuid4()}@example.com", "password": "StrongPass123!"})
    assert_error(response, 503, "SERVICE_UNAVAILABLE")


def test_a_bad_verification_token_is_token_invalid(client):
    assert_error(client.post("/identity/verify-email", json={"token": "nope"}), 401, "TOKEN_INVALID")


@pytest.mark.asyncio
async def test_a_result_before_submission_is_attempt_not_submitted(client):
    _, student, _, attempt, _ = await started_attempt(client)
    response = client.get(f"/assessment/attempts/{attempt['id']}/result", headers=student)
    assert_error(response, 409, "ATTEMPT_NOT_SUBMITTED")


# --- public messages -----------------------------------------------------------------------


class _Needs(BaseModel):
    number: int


def _library_errors():
    try:
        _Needs(number="the-secret-value")
    except ValidationError as exc:
        yield exc
    try:
        json.loads("the-secret-value")
    except ValueError as exc:
        yield exc
    try:
        b"\xff-the-secret-value".decode("utf-8")
    except ValueError as exc:
        yield exc


@pytest.mark.parametrize("error", list(_library_errors()), ids=lambda e: type(e).__name__)
def test_a_library_error_never_reaches_a_client_as_text(error):
    assert isinstance(error, ValueError)
    assert public_message(error, "fallback") == "fallback"


def test_a_message_written_for_clients_is_kept():
    assert public_message(AppError("written here"), "fallback") == "written here"


# --- the last resort -----------------------------------------------------------------------

ORIGIN = "https://app.build.example"


def _broken_app() -> FastAPI:
    broken = FastAPI()
    add_response_middleware(broken, [ORIGIN])

    @broken.get("/boom")
    async def boom():
        raise RuntimeError(INTERNAL)

    return broken


def test_the_real_app_answers_failures_inside_its_stack():
    assert UnhandledErrorMiddleware in [m.cls for m in app.user_middleware]


def test_an_unexpected_failure_passes_back_through_security_headers_and_cors():
    # No raise_server_exceptions=False: the failure must be answered, not escape.
    with TestClient(_broken_app()) as broken:
        response = broken.get("/boom", headers={"Origin": ORIGIN, "X-Request-ID": "trace-1"})
    assert_error(response, 500, "INTERNAL_ERROR")
    assert response.json()["meta"]["request_id"] == "trace-1"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert "secret-detail" not in response.text


def test_another_origin_gets_no_cors_permission_from_a_failure():
    with TestClient(_broken_app()) as broken:
        response = broken.get("/boom", headers={"Origin": "https://elsewhere.example"})
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_a_failure_after_the_response_started_is_not_replaced():
    async def started_then_failed(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError(INTERNAL)

    sent = []

    async def send(message):
        sent.append(message)

    with pytest.raises(RuntimeError):
        await UnhandledErrorMiddleware(started_then_failed)({"type": "http"}, None, send)
    assert [m["type"] for m in sent] == ["http.response.start"]


def test_a_failure_in_the_middleware_itself_still_gets_the_backstop():
    broken = FastAPI()
    broken.add_exception_handler(Exception, unhandled_exception_handler)

    @broken.middleware("http")
    async def fails(request, call_next):
        raise RuntimeError(INTERNAL)

    with TestClient(broken, raise_server_exceptions=False) as surviving:
        response = surviving.get("/anything")
    assert_error(response, 500, "INTERNAL_ERROR")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "secret-detail" not in response.text
