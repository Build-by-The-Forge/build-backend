"""S-02 on real PostgreSQL, through the routes: input PostgreSQL itself
would refuse with an error, and another tenant's references."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api import identity as identity_api
from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from pg_smoke.accounts import register_and_get_id
from pg_smoke.test_migration_0032 import _world

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"


async def _signed_in(client, w: dict[str, str]) -> dict[str, str]:
    email = f"s02-{uuid4().hex}@example.com"
    user_id = await register_and_get_id(client, {"email": email, "password": PASSWORD})
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})
    login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            MembershipModel(
                id=str(uuid4()),
                tenant_id=w["tenant"],
                user_id=user_id,
                role="student",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        slug = await session.scalar(select(TenantModel.slug).where(TenantModel.id == w["tenant"]))
        await session.commit()
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}", "X-Tenant-Slug": slug}


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"programme_id": "p\x00"}, "programme_id"),
        ({"course_ids": ["c\x00"]}, "course_ids"),
        ({"level": 2**40}, "level"),
        ({"level": -(2**40)}, "level"),
    ],
)
async def test_input_postgresql_cant_hold_is_unavailable_not_a_server_error(client, change, field):
    w = await _world()
    student = await _signed_in(client, w)
    body = {"programme_id": w["programme"], "level": 300, "course_ids": [w["course"]], **change}

    response = await client.put("/academic/profile", json=body, headers=student)

    assert response.status_code == 422, response.text
    assert [f["field"] for f in response.json()["error"]["details"]["fields"]] == [f"body.{field}"]


async def test_another_tenants_references_get_the_same_answer_as_unknown_ones(client):
    w, other = await _world(300), await _world(700)
    student = await _signed_in(client, w)
    answers = []
    for body in (
        {"programme_id": other["programme"], "level": 700, "course_ids": [other["course"]]},
        {"programme_id": str(uuid4()), "level": 999, "course_ids": [str(uuid4())]},
    ):
        response = await client.put("/academic/profile", json=body, headers=student)
        assert response.status_code == 422
        answers.append(response.json()["error"])

    assert answers[0] == answers[1]
    saved = await client.put(
        "/academic/profile", json={"programme_id": w["programme"], "level": 300, "course_ids": [w["course"]]}, headers=student
    )
    assert saved.status_code == 200 and saved.json()["data"]["complete"] is True
