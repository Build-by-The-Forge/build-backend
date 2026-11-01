"""One error shape with stable codes (M3-A): what a client branches on, and what
it must never be told."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.catalogue import courses
from app.main import app
from tests.integration.assessment.test_assessment_visibility import assessment_with_question
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
    with TestClient(app, raise_server_exceptions=False) as surviving:
        response = surviving.get("/catalogue/courses/", headers=student)
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
