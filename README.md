# build-backend

This repository now contains a starter foundation for a modular monolith backend built with FastAPI, SQLAlchemy async, PostgreSQL, Redis, Alembic, Docker Compose, and a basic CI workflow.

## Structure

- app/api: API routers and endpoints
- app/application: use cases and application services
- app/domain: business entities and domain rules
- app/infrastructure: integrations and external service implementations
- app/core: configuration and logging
- app/db: database session and persistence wiring
- tests: automated tests

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

## Docker

```bash
docker compose up --build
```

## Verification

```bash
pytest -q
```
