"""The structure reads against the schema production gets, past the point where PostgreSQL
moves a repeated statement to a generic plan."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api import identity as identity_api
from app.db.session import SessionLocal
from pg_smoke.accounts import register_and_get_id

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"


async def _insert(session, table: str, columns: dict) -> None:
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    await session.execute(text(f"insert into {table} ({names}) values ({values})"), columns)


async def institution(client, role: str = "student") -> tuple[dict, dict]:
    now = datetime.now(timezone.utc)
    stamps = {"status": "active", "created_at": now, "updated_at": now}
    tenant_id, slug = str(uuid4()), f"struct-{uuid4().hex[:10]}"
    school, closed, department = str(uuid4()), str(uuid4()), str(uuid4())
    hidden = str(uuid4())
    email = f"struct-{uuid4().hex}@example.com"
    user_id = await register_and_get_id(client, {"email": email, "password": PASSWORD})
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})
    login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    async with SessionLocal() as session:
        await _insert(session, "tenants", {"id": tenant_id, "name": "Institution", "slug": slug, **stamps})
        await session.commit()
        for row_id, name, status in ((school, "School of Computing", "active"), (closed, "Closed school", "archived")):
            await _insert(
                session,
                "faculties",
                {"id": row_id, "tenant_id": tenant_id, "name": name, "slug": row_id[:30], **stamps, "status": status},
            )
        for row_id, faculty, name in ((department, school, "Department of Software Engineering"), (hidden, closed, "Hidden")):
            await _insert(
                session,
                "departments",
                {
                    "id": row_id,
                    "tenant_id": tenant_id,
                    "faculty_id": faculty,
                    "name": name,
                    "slug": row_id[:30],
                    "code": row_id[:12],
                    **stamps,
                },
            )
        for row_id, faculty, parent, name in (
            (str(uuid4()), school, department, "B.Tech. Software Engineering"),
            (str(uuid4()), closed, hidden, "Hidden programme"),
        ):
            await _insert(
                session,
                "programmes",
                {
                    "id": row_id,
                    "tenant_id": tenant_id,
                    "faculty_id": faculty,
                    "department_id": parent,
                    "name": name,
                    "slug": row_id[:30],
                    "code": row_id[:12],
                    "duration_years": 4,
                    **stamps,
                },
            )
        await _insert(
            session,
            "memberships",
            {"id": str(uuid4()), "tenant_id": tenant_id, "user_id": user_id, "role": role, **stamps},
        )
        await session.commit()
    reader = {"Authorization": f"Bearer {login.json()['data']['access_token']}", "X-Tenant-Slug": slug}
    return reader, {"school": school, "department": department}


async def test_the_structure_reads_on_the_migrated_schema(client):
    reader, ids = await institution(client)

    for _ in range(7):
        faculties = await client.get("/catalogue/faculties", headers=reader)
        departments = await client.get(f"/catalogue/departments?faculty_id={ids['school']}", headers=reader)
        programmes = await client.get(f"/catalogue/programmes?department_id={ids['department']}&limit=1", headers=reader)

        assert [item["name"] for item in faculties.json()["data"]] == ["School of Computing"]
        assert [item["name"] for item in departments.json()["data"]] == ["Department of Software Engineering"]
        assert [item["name"] for item in programmes.json()["data"]] == ["B.Tech. Software Engineering"]
        assert programmes.json()["meta"]["pagination"] == {"total": 1, "limit": 1, "offset": 0}

    everything = await client.get("/catalogue/programmes", headers=reader)
    assert [item["name"] for item in everything.json()["data"]] == ["B.Tech. Software Engineering"]
