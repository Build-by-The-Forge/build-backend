FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only: the pinned closure (requirements.txt), mounted
# for the install so no requirements file stays in the image. The project
# itself is not installed: the app runs from /app.
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --upgrade pip && pip install --no-cache-dir -r /tmp/requirements.txt

# What production runs, and nothing else: the app, its migrations and the
# tenant-provisioning command (python -m scripts.provision_tenant).
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts/provision_tenant.py ./scripts/provision_tenant.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Test tooling and tests on top of the same runtime. Built only on request
# (`--target test`; compose's boundary-tests service); never published.
FROM runtime AS test

RUN --mount=type=bind,source=requirements-dev.txt,target=/tmp/requirements-dev.txt \
    --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements-dev.txt

COPY pyproject.toml ./
COPY scripts ./scripts
COPY tests ./tests
COPY pg_smoke ./pg_smoke
COPY boundary ./boundary


# The default (last) stage: a plain `docker build .` gives the runtime image.
FROM runtime AS production
