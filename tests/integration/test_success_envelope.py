"""One success shape (M3-A, G-20): {success, data, error, meta}, with the request ID in
meta. The drift gate probes routes as a student; these cover what it can't reach."""

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.responses import JSONResponse

from tests.integration.assessment.test_assessment_visibility import assessment_with_question

API = Path(__file__).resolve().parents[2] / "app" / "api"
# Staff-only routes and the signed callback, which keep their contract for now.
OUTSIDE_THE_CONTRACT = {"content/jobs.py"}
PASSWORD = "StrongPass123!"
# Retired routes answer 410 from a constant, for one release, and aren't in the contract.
RETIRED_BODIES = {"REGISTRATION_RETIRED", "VERSION_RETIRED"}


def assert_success(response, status_code=200):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta"}
    assert body["success"] is True and body["error"] is None
    assert body["meta"]["request_id"] == response.headers["x-request-id"]
    return body["data"]


def _route_modules():
    for path in API.rglob("*.py"):
        if path.relative_to(API).as_posix() not in OUTSIDE_THE_CONTRACT:
            yield path, ast.parse(path.read_text("utf-8"))


def _key_names(node: ast.Dict) -> set[str]:
    return {key.value for key in node.keys if isinstance(key, ast.Constant)}


def test_every_success_body_on_a_route_has_the_contracts_shape():
    problems = []
    checked = 0
    for path, tree in _route_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = _key_names(node)
            if "data" not in keys or not ({"success", "meta"} & keys or keys == {"data"}):
                continue
            checked += 1
            where = f"{path.relative_to(API)}:{node.lineno}"
            if keys != {"success", "data", "error", "meta"}:
                problems.append(f"{where} {sorted(keys)}")
                continue
            meta = node.values[[getattr(k, "value", None) for k in node.keys].index("meta")]
            if not isinstance(meta, ast.Dict) or "request_id" not in _key_names(meta):
                problems.append(f"{where} no request_id in meta")
    assert checked > 50, "the check must find what it guards"
    assert not problems, " | ".join(problems)


def test_every_json_response_on_a_route_is_built_from_a_literal_body():
    problems = []
    for path, tree in _route_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == JSONResponse.__name__:
                content = [k.value for k in node.keywords if k.arg == "content"]
                if content and getattr(content[0], "id", "") in RETIRED_BODIES:
                    continue
                if not content or not isinstance(content[0], ast.Dict):
                    problems.append(f"{path.relative_to(API)}:{node.lineno}")
    assert not problems, " | ".join(problems)


def test_the_identity_flow_succeeds_in_the_contracts_shape(client):
    payload = {"email": f"shape-{uuid4()}@example.com", "password": PASSWORD}
    assert client.post("/identity/users", json=payload).status_code == 202

    issued = assert_success(client.post("/identity/authenticate", json=payload))
    bearer = {"Authorization": f"Bearer {issued['access_token']}"}
    assert assert_success(client.get("/identity/me", headers=bearer))["email"] == payload["email"]
    assert isinstance(assert_success(client.get("/identity/memberships", headers=bearer)), list)

    refreshed = assert_success(client.post("/identity/refresh", json={"refresh_token": issued["refresh_token"]}))
    bearer = {"Authorization": f"Bearer {refreshed['access_token']}"}
    assert_success(client.post("/identity/logout", headers=bearer))


def test_a_message_only_success_keeps_its_message_in_meta(client):
    response = client.post("/identity/forgot-password", json={"email": f"nobody-{uuid4()}@example.com"})
    assert_success(response)
    assert response.json()["meta"]["message"]


@pytest.mark.asyncio
async def test_a_paginated_list_keeps_its_counts_beside_the_request_id(client):
    _, student, _, _ = await assessment_with_question(client, published=True)
    response = client.get("/content/assets?limit=7&offset=0", headers=student)
    assert isinstance(assert_success(response), list)
    meta = response.json()["meta"]
    assert (meta["limit"], meta["offset"]) == (7, 0)
    assert meta["total"] >= 0


def test_a_client_request_id_comes_back_in_the_body(client):
    payload = {"email": f"shape-{uuid4()}@example.com", "password": PASSWORD}
    assert client.post("/identity/users", json=payload).status_code == 202
    response = client.post("/identity/authenticate", json=payload, headers={"X-Request-ID": "trace-2"})
    assert response.json()["meta"]["request_id"] == "trace-2"
    assert "request_id" not in response.json()


def test_the_root_route_has_the_shape(client):
    assert_success(client.get("/"))
