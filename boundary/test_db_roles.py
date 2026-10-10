"""AI-service's database role on the shared database (C24, C25; design B.6)."""

import asyncio
import uuid

import asyncpg
import pytest

from boundary.conftest import AI_APP_DSN


def run(statement: str, *args):
    async def go():
        connection = await asyncpg.connect(AI_APP_DSN)
        try:
            return await connection.fetch(statement, *args)
        finally:
            await connection.close()

    return asyncio.run(go())


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM users LIMIT 1",
        "UPDATE memberships SET role = 'owner'",
        "INSERT INTO questions (id) VALUES ('x')",
        "SELECT * FROM tenants LIMIT 1",
        "SELECT * FROM content_ingestion_jobs LIMIT 1",
        "DELETE FROM security_events",
        "SELECT * FROM alembic_version",
    ],
)
def test_c24_ai_service_cannot_touch_backend_tables(statement):
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        run(statement)


def test_c24_ai_service_cannot_create_objects():
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        run("CREATE TABLE ai_shadow (id int)")


def test_c25_ai_service_can_use_its_own_tables():
    tenant, user = str(uuid.uuid4()), str(uuid.uuid4())
    run(
        "INSERT INTO learning_memory (tenant_id, user_id, topic, mastery_score, attempts, last_interaction)"
        " VALUES ($1, $2, 'c25', 0.1, 1, '')",
        tenant,
        user,
    )
    run("UPDATE learning_memory SET attempts = 2 WHERE tenant_id = $1", tenant)
    assert run("SELECT attempts FROM learning_memory WHERE tenant_id = $1", tenant)[0]["attempts"] == 2
    run(
        "INSERT INTO session_memory (tenant_id, session_id, user_id, context, message_count) VALUES ($1, 's', $2, '', 0)",
        tenant,
        user,
    )
    run("DELETE FROM session_memory WHERE tenant_id = $1", tenant)
    run("DELETE FROM learning_memory WHERE tenant_id = $1", tenant)
