import pytest

from app.infrastructure.db.models.tenant_core import TenantModel, FacultyModel, DepartmentModel
from datetime import datetime, timezone
import uuid


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
async def test_whoami_valid_token_for_nonexistent_user(client, session):
    # craft token for non-existent user
    # token service in tests encodes subject directly
    fake_token = "access:nonexistent-user-id"
    headers = {"Authorization": f"Bearer {fake_token}"}
    who = client.get("/identity/whoami", headers=headers)
    assert who.status_code == 401
    data = who.json()
    assert data["success"] is False
