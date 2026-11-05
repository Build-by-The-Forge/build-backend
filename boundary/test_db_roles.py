"""AI-service's database role on the shared database (C24, C25; design B.6)."""

import asyncio
import os
import uuid

import asyncpg
import pytest

from boundary.conftest import AI_APP_DSN

BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")
# The tables migration 0030 added (M3-D).
M3D_TABLES = (
    "content_blobs",
    "content_ownership_classifications",
    "content_scans",
    "content_rights_assertions",
    "content_publications",
    "content_upload_usage",
    "content_retry_usage",
)


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
        "SELECT * FROM content_blobs LIMIT 1",
        "SELECT * FROM content_rights_assertions LIMIT 1",
        "SELECT * FROM content_publications LIMIT 1",
        "UPDATE content_ownership_classifications SET new_class = 'x'",
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


def test_c25_ai_service_can_use_its_index_fence():
    # ingestion_fences (ai-service P3-6 §7.5): the runtime role raises a
    # fence (upsert), reads it under a row lock, and removes it.
    tenant = str(uuid.uuid4())
    for attempt in (2, 1):
        run(
            "INSERT INTO ingestion_fences (tenant_id, asset_id, run_number, attempt) VALUES ($1, 'c25', 1, $2)"
            " ON CONFLICT (tenant_id, asset_id) DO UPDATE SET run_number = EXCLUDED.run_number,"
            " attempt = EXCLUDED.attempt"
            " WHERE (EXCLUDED.run_number, EXCLUDED.attempt) > (ingestion_fences.run_number, ingestion_fences.attempt)",
            tenant,
            attempt,
        )
    [row] = run(
        "SELECT run_number, attempt FROM ingestion_fences WHERE tenant_id = $1 AND asset_id = 'c25' FOR UPDATE",
        tenant,
    )
    assert (row["run_number"], row["attempt"]) == (1, 2)  # the fence never lowered
    run("DELETE FROM ingestion_fences WHERE tenant_id = $1", tenant)


def test_c25_ai_service_can_use_its_chunk_index():
    # document_chunks (ai-service P3-4): pgvector and the generated
    # full-text column work for the runtime role, not only the owner.
    tenant = str(uuid.uuid4())
    run(
        "INSERT INTO document_chunks (chunk_id, tenant_id, asset_id, run_number, chunk_index,"
        " page_start, page_end, content, embedding, embedding_model)"
        " VALUES ($1, $2, 'c25', 1, 0, 1, 1, 'Charges repel', $3::text::vector, 'c25')",
        str(uuid.uuid4()),
        tenant,
        "[" + ",".join(["1"] + ["0"] * 383) + "]",
    )
    [row] = run(
        "SELECT embedding <=> $2::text::vector AS distance,"
        " content_tsv @@ plainto_tsquery('english', 'repelling charge') AS matches"
        " FROM document_chunks WHERE tenant_id = $1",
        tenant,
        "[" + ",".join(["1"] + ["0"] * 383) + "]",
    )
    assert row["distance"] == 0 and row["matches"] is True
    run("DELETE FROM document_chunks WHERE tenant_id = $1", tenant)


def test_c25_ai_service_can_use_its_scope_table():
    # asset_scopes (ai-service M3-D): the runtime role applies an assignment
    # only above the stored version, and reads it.
    tenant = str(uuid.uuid4())
    for scope, version in (("institutional", 2), ("unknown", 1)):
        run(
            "INSERT INTO asset_scopes (tenant_id, asset_id, scope, version) VALUES ($1, 'c25', $2, $3)"
            " ON CONFLICT (tenant_id, asset_id) DO UPDATE SET scope = EXCLUDED.scope, version = EXCLUDED.version"
            " WHERE EXCLUDED.version > asset_scopes.version",
            tenant,
            scope,
            version,
        )
    [row] = run("SELECT scope, version FROM asset_scopes WHERE tenant_id = $1 AND asset_id = 'c25'", tenant)
    assert (row["scope"], row["version"]) == ("institutional", 2)  # the older assignment changed nothing
    run("DELETE FROM asset_scopes WHERE tenant_id = $1", tenant)


def test_the_backend_runtime_role_can_use_the_m3d_tables_it_does_not_own():
    # Migration 0030 ran as the owner role; default privileges give the
    # runtime role what the routes need, and nothing makes it the owner.
    async def go():
        connection = await asyncpg.connect(BACKEND_APP_DSN)
        try:
            return await connection.fetch(
                "SELECT t.name, c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user) AS not_owner,"
                " has_table_privilege(current_user, c.oid, 'SELECT, INSERT, UPDATE, DELETE') AS usable"
                " FROM unnest($1::text[]) AS t(name) LEFT JOIN pg_class c ON c.relname = t.name AND c.relkind = 'r'",
                list(M3D_TABLES),
            )
        finally:
            await connection.close()

    rows = asyncio.run(go())
    assert {row["name"]: (row["not_owner"], row["usable"]) for row in rows} == {name: (True, True) for name in M3D_TABLES}
