FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only: the pinned closure (requirements.txt), mounted
# for the install so no requirements file stays in the image. The project
# itself is not installed: the app runs from /app.
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --upgrade pip && pip install --no-cache-dir -r /tmp/requirements.txt

# The unprivileged user the service runs as (UID/GID 10001, no login shell,
# no home). Code and packages stay root-owned, so it cannot change them; its
# only writable paths are /tmp and /outbox (the development email outbox; a
# named volume takes this directory's ownership when first created).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin app \
    && install -d -o app -g app -m 0750 /outbox

# What production runs, and nothing else: the app, its migrations and the
# tenant-provisioning command (python -m scripts.provision_tenant).
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts/provision_tenant.py ./scripts/provision_tenant.py

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Test tooling and tests on top of the same runtime. Built only on request
# (`--target test`; compose's boundary-tests service); never published.
FROM runtime AS test

# Installing needs root; the tests then run as the same user as production.
USER root

RUN --mount=type=bind,source=requirements-dev.txt,target=/tmp/requirements-dev.txt \
    --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements-dev.txt

COPY pyproject.toml ./
COPY scripts ./scripts
COPY tests ./tests
COPY pg_smoke ./pg_smoke
COPY boundary ./boundary

USER 10001:10001


# The default (last) stage: a plain `docker build .` gives the runtime image.
FROM runtime AS production
