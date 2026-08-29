from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.infrastructure.db.models.assessment  # noqa: F401
import app.infrastructure.db.models.benchmark  # noqa: F401
import app.infrastructure.db.models.catalogue  # noqa: F401
import app.infrastructure.db.models.curriculum  # noqa: F401
import app.infrastructure.db.models.tenant_core  # noqa: F401
import app.infrastructure.identity.models  # noqa: F401
from app.db.base import Base

config = context.config
# allow overriding the DB URL from the environment (useful in CI/production)
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    # enable batch mode for sqlite in offline mode to allow alter-like operations
    render_as_batch = False
    if url is not None and "sqlite" in url:
        render_as_batch = True
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=render_as_batch,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # enable batch mode for sqlite to support operations that require table copy-and-move
        render_as_batch = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=render_as_batch,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
