# Alembic

Migrations in `alembic/versions` are the only definition of the production
schema. The ORM models must describe the same schema; the test suite's
SQLite database is built from the models with `create_all`, so it cannot
show that the two agree.

## Rule

A change to a persistent ORM model (columns, types, nullability,
relationships backed by columns, constraints, indexes) is incomplete until:

1. an Alembic migration makes the same change, and
2. it has been verified against a PostgreSQL database built only by
   `alembic upgrade head` (no `create_all`): the drift check passes and the
   affected endpoints work with realistic related records.

The CI PostgreSQL gate enforces the drift check and a smoke run; review
enforces the rest.

## Migration conventions

- Run on both PostgreSQL and SQLite (`render_as_batch` on SQLite; no
  dialect-only SQL without a guard).
- Never silently rewrite or delete data. When existing rows would block or
  be changed ambiguously by a migration, refuse with a report of what was
  found and let an operator decide (see 0018, 0019).
- The backend owns its tables and the `alembic_version` table;
  AI-service migrations use `ai_service_alembic_version`.

## Known, accepted differences

`alembic check` currently also reports the deferred catalogue models
(`curriculum_versions`, `course_prerequisites`) and some identity indexes
and constraints present in the database but not declared on the models;
see `docs/phase1-m2-schema-drift-investigation.md`. The CI gate allows
exactly these and fails on anything else.
