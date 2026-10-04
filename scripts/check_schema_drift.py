"""Fail if the ORM models and a migrated database disagree.

Usage: DATABASE_URL=postgresql+asyncpg://... python scripts/check_schema_drift.py

Run against a database built only by `alembic upgrade head`. Differences
listed in ALLOWED are known and accepted
(docs/phase1-m2-schema-drift-investigation.md); anything else fails.
"""

import asyncio
import os
import sys
from typing import Any

import app.main  # noqa: F401  (imports every model onto Base.metadata)
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

# Models whose design is deferred; they are marked "NOT MIGRATED".
DEFERRED_TABLES = frozenset({"curriculum_versions", "course_prerequisites"})
# Present in the database, not declared on the models (harmless).
ALLOWED_DB_ONLY_INDEXES = frozenset(
    {
        "idx_devices_device_fingerprint",
        "idx_login_events_created_at",
        "idx_login_events_user_id",
        "idx_sessions_refresh_token_hash",
        "idx_sessions_user_id",
    }
)
# users.status: VARCHAR(50) in the database, non-native enum on the model.
ALLOWED_TYPE_CHANGES = frozenset({("users", "status")})


def _table(diff: tuple[Any, ...]) -> str | None:
    op = diff[0]
    if op in ("add_column", "remove_column", "modify_type", "modify_nullable"):
        return diff[2]
    if op in ("add_table", "remove_table"):
        return diff[1].name
    target = diff[1]
    return getattr(getattr(target, "table", None), "name", None)


def is_allowed(diff: tuple[Any, ...]) -> bool:
    op = diff[0]
    if _table(diff) in DEFERRED_TABLES:
        return True
    if op == "remove_index":
        return diff[1].name in ALLOWED_DB_ONLY_INDEXES
    if op == "modify_type":
        return (diff[2], diff[3]) in ALLOWED_TYPE_CHANGES
    return False


def flatten(diffs: list[Any]) -> list[tuple[Any, ...]]:
    flat: list[tuple[Any, ...]] = []
    for diff in diffs:
        if isinstance(diff, list):
            flat.extend(flatten(diff))
        else:
            flat.append(diff)
    return flat


def _compare(connection: Any) -> list[Any]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(context, Base.metadata)


async def find_unexpected_drift(database_url: str) -> list[tuple[Any, ...]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            diffs = await connection.run_sync(_compare)
    finally:
        await engine.dispose()
    return [diff for diff in flatten(diffs) if not is_allowed(diff)]


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        print("DATABASE_URL must point at a migrated PostgreSQL database")
        return 2
    unexpected = asyncio.run(find_unexpected_drift(url))
    if unexpected:
        print(f"Schema drift between ORM models and migrations ({len(unexpected)}):")
        for diff in unexpected:
            print(f"  {_table(diff)}: {diff[0]}")
        print("Add a migration (docs/alembic.md) or, if intended, update ALLOWED.")
        return 1
    print("No unexpected schema drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
