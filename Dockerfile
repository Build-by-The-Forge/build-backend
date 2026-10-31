# Pinned base image: the patch release and its multi-platform index digest,
# resolved 2026-10-13 (the same image python:3.13-slim pointed to). To
# upgrade: pull the new patch tag, take its digest from
# `docker buildx imagetools inspect python:<version>-slim`, update both here,
# and run scripts/m3_boundary_gate.sh before committing.
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only: the pinned closure (requirements.txt), mounted
# for the install so no requirements file stays in the image. The project
# itself is not installed: the app runs from /app.
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir pip==26.2.1 && pip install --no-cache-dir -r /tmp/requirements.txt

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


# The default (last) stage, and what production runs: the runtime image plus a
# marker that makes the service refuse learning memory while the production
# gate is closed, whatever APP_ENVIRONMENT says (app/core/learning_memory_gate.py).
# A file, since an ENV could be overridden at runtime. Only the boundary gate's
# development topology builds --target runtime, to exercise memory.
FROM runtime AS production

USER root

RUN install -d -m 0755 /opt/build-backend && touch /opt/build-backend/production-image \
    && chmod 0444 /opt/build-backend/production-image

USER 10001:10001
