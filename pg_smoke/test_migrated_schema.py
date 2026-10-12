import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api import identity as identity_api
from app.db.session import SessionLocal
from scripts.check_schema_drift import find_unexpected_drift

# The app has one engine whose pooled asyncpg connections belong to the loop
# that opened them, so every test here shares one session-wide loop.
pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"

INSERT_TENANT = (
    "insert into tenants (id, name, slug, status, created_at, updated_at) values (:id, 'Smoke', :slug, 'active', :now, :now)"
)
_INSERT_MEMBERSHIP = (
    "insert into memberships (id, tenant_id, user_id, role, status, created_at, updated_at) "
    "values (:id, :t, :u, '{role}', 'active', :now, :now)"
)
INSERT_ADMIN_MEMBERSHIP = _INSERT_MEMBERSHIP.format(role="admin")
INSERT_STUDENT_MEMBERSHIP = _INSERT_MEMBERSHIP.format(role="student")
INSERT_FACULTY = (
    "insert into faculties (id, tenant_id, name, slug, status, created_at, updated_at) "
    "values (:id, :t, 'F', :slug, 'active', :now, :now)"
)
INSERT_DEPARTMENT = (
    "insert into departments (id, tenant_id, faculty_id, name, slug, code, status, created_at, updated_at) "
    "values (:id, :t, :f, 'D', :slug, :code, 'active', :now, :now)"
)


async def _verified_admin(client) -> tuple[dict[str, str], str]:
    """A verified user who is admin of a fresh tenant with one department."""
    email = f"smoke-{uuid4().hex}@example.com"
    user_id = (await client.post("/identity/users", json={"email": email, "password": PASSWORD})).json()["data"]["id"]
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    assert (await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})).status_code == 200
    token = (await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})).json()["data"][
        "access_token"
    ]

    now = datetime.now(timezone.utc)
    tenant_id, faculty_id, department_id = (str(uuid4()) for _ in range(3))
    slug = f"smoke-{uuid4().hex[:10]}"
    async with SessionLocal() as session:
        for statement, params in (
            (
                INSERT_TENANT,
                {"id": tenant_id, "slug": slug},
            ),
            (
                INSERT_ADMIN_MEMBERSHIP,
                {"id": str(uuid4()), "t": tenant_id, "u": user_id},
            ),
            (
                INSERT_FACULTY,
                {"id": faculty_id, "t": tenant_id, "slug": f"f-{slug}"},
            ),
            (
                INSERT_DEPARTMENT,
                {
                    "id": department_id,
                    "t": tenant_id,
                    "f": faculty_id,
                    "slug": f"d-{slug}",
                    "code": f"D{uuid4().hex[:6].upper()}",
                },
            ),
        ):
            await session.execute(text(statement), {**params, "now": now})
        await session.commit()
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": slug}, department_id


async def test_models_match_the_migrated_schema():
    assert await find_unexpected_drift(os.environ["DATABASE_URL"]) == []


async def test_catalogue_and_questions_work_with_related_records(client):
    headers, department_id = await _verified_admin(client)

    async def ok(method, path, expected=200, **kw):
        response = await client.request(method, path, headers=headers, **kw)
        assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text}"
        return response.json()["data"]

    course = await ok(
        "POST",
        "/catalogue/courses/",
        201,
        json={
            "department_id": department_id,
            "code": "CSC201",
            "title": "Algorithms",
            "slug": "algorithms",
            "credit_units": 3,
            "level": 200,
            "semester": 1,
            "description": "Intro",
        },
    )
    topic = await ok("POST", f"/catalogue/courses/{course['id']}/topics", 201, json={"title": "Sorting", "slug": "sorting"})
    outcome = await ok(
        "POST",
        f"/catalogue/topics/{topic['id']}/learning-outcomes",
        201,
        json={"sequence": 1, "description": "Explain quicksort"},
    )
    material = await ok(
        "POST", f"/catalogue/topics/{topic['id']}/reference-materials", 201, json={"title": "CLRS", "material_type": "book"}
    )

    # Reads load the course together with its topics, outcomes and materials.
    await ok("GET", "/catalogue/courses/")
    await ok("GET", f"/catalogue/courses/{course['id']}")
    assert [t["id"] for t in await ok("GET", f"/catalogue/courses/{course['id']}/topics")] == [topic["id"]]
    assert [o["id"] for o in await ok("GET", f"/catalogue/topics/{topic['id']}/learning-outcomes")] == [outcome["id"]]
    assert [m["id"] for m in await ok("GET", f"/catalogue/topics/{topic['id']}/reference-materials")] == [material["id"]]
    await ok("PATCH", f"/catalogue/courses/{course['id']}", json={"title": "Algorithms II"})
    await ok("PATCH", f"/catalogue/topics/{topic['id']}", json={"title": "Sorting II"})

    question = await ok(
        "POST",
        "/assessment/questions",
        201,
        json={
            "topic_id": topic["id"],
            "learning_outcome_id": outcome["id"],
            "question_type": "mcq",
            "prompt": "Quicksort worst case?",
            "explanation": "Bad pivots.",
            "difficulty": "medium",
            "marks": 2,
            "options": [
                {"text": "O(n^2)", "display_order": 1, "is_correct": True},
                {"text": "O(1)", "display_order": 2, "is_correct": False},
            ],
        },
    )
    read = await ok("GET", f"/assessment/questions/{question['id']}")
    assert (read["topic_id"], read["learning_outcome_id"]) == (topic["id"], outcome["id"])


async def test_memberships_require_an_existing_user():
    now = datetime.now(timezone.utc)
    tenant_id = str(uuid4())
    async with SessionLocal() as session:
        await session.execute(
            text(INSERT_TENANT),
            {"id": tenant_id, "slug": f"fk-{uuid4().hex[:10]}", "now": now},
        )
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(
                text(INSERT_STUDENT_MEMBERSHIP),
                {"id": str(uuid4()), "t": tenant_id, "u": str(uuid4()), "now": now},
            )


async def test_sign_in_writes_security_records(client):
    email = f"smoke-{uuid4().hex}@example.com"
    user_id = (await client.post("/identity/users", json={"email": email, "password": PASSWORD})).json()["data"]["id"]
    assert (await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})).status_code == 200

    async with SessionLocal() as session:
        logins = (
            await session.execute(text("select count(*) from login_events where user_id = :u and successful"), {"u": user_id})
        ).scalar_one()
        events = (
            await session.execute(
                text("select count(*) from security_events where user_id = :u and action = 'registered'"), {"u": user_id}
            )
        ).scalar_one()
    assert (logins, events) == (1, 1)


@pytest.mark.xfail(strict=True, reason="known: unregistered device_id hits sessions.device_id FK -> 500 (hardening list)")
async def test_sign_in_with_an_unregistered_device_id_is_a_client_error(client):
    email = f"smoke-{uuid4().hex}@example.com"
    await client.post("/identity/users", json={"email": email, "password": PASSWORD})

    response = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD, "device_id": str(uuid4())})

    assert response.status_code < 500
