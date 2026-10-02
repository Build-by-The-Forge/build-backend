from uuid import uuid4

import jwt
import pytest

from app.infrastructure.security.jwt_token_service import JWTTokenService


@pytest.mark.asyncio
async def test_whoami_requires_token(client, session):
    resp = client.get("/identity/whoami")
    assert resp.status_code == 401
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_whoami_malformed_header(client, session):
    headers = {"Authorization": "BadToken"}
    resp = client.get("/identity/whoami", headers=headers)
    assert resp.status_code == 401
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_whoami_valid_token_for_existing_user(client, session):
    # register a user
    payload = {"email": "a@example.com", "password": "StrongPass123!"}
    r = client.post("/identity/users", json=payload)
    assert r.status_code == 201
    user = r.json()["data"]

    auth = client.post("/identity/authenticate", json=payload)
    assert auth.status_code == 200
    tokens = auth.json()["data"]
    access_token = tokens["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    who = client.get("/identity/whoami", headers=headers)
    assert who.status_code == 200
    data = who.json()
    assert data["success"] is True
    assert data["data"]["user_id"] == user["id"]


@pytest.mark.asyncio
async def test_whoami_signed_token_for_nonexistent_user(client, session):
    token = JWTTokenService().issue_access_token("nonexistent-user-id", "some-session")
    who = client.get("/identity/whoami", headers={"Authorization": f"Bearer {token}"})
    assert who.status_code == 401
    assert who.json()["success"] is False


def _register_and_login(client):
    payload = {"email": f"victim-{uuid4().hex}@example.com", "password": "StrongPass123!"}
    user_id = client.post("/identity/users", json=payload).json()["data"]["id"]
    tokens = client.post("/identity/authenticate", json=payload).json()["data"]
    return user_id, tokens


@pytest.mark.asyncio
@pytest.mark.parametrize("forge", ["{uid}", "access:{uid}", "refresh:{uid}"])
async def test_tokens_forged_from_a_user_id_are_rejected(client, session, forge):
    user_id, _ = _register_and_login(client)
    for path in ("/identity/whoami", "/identity/me"):
        resp = client.get(path, headers={"Authorization": f"Bearer {forge.format(uid=user_id)}"})
        assert resp.status_code == 401, path


@pytest.mark.asyncio
async def test_refresh_token_is_not_accepted_as_an_access_token(client, session):
    _, tokens = _register_and_login(client)
    resp = client.get(
        "/identity/whoami", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tampered_and_unsigned_tokens_are_rejected(client, session):
    user_id, tokens = _register_and_login(client)
    header, payload, signature = tokens["access_token"].split(".")

    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"
    unsigned = jwt.encode({"sub": user_id, "sid": "x", "typ": "access"}, None, algorithm="none")

    for bad in (tampered, unsigned):
        resp = client.get("/identity/whoami", headers={"Authorization": f"Bearer {bad}"})
        assert resp.status_code == 401
