# build-backend

This repository now contains a completed backend foundation for a modular monolith backend built with FastAPI, SQLAlchemy async, PostgreSQL, Redis, Alembic, Docker Compose, and CI.

## Milestones

- v0.1.0-foundation: platform foundation complete
- Phase 2: Identity & Access Management (IAM)

## Current platform capabilities

- Configuration management with typed settings
- Structured logging and request context
- Metrics and tracing hooks
- Middleware for request context and security headers
- Global exception handling
- Async database session and unit-of-work foundation
- Redis abstraction and AI gateway skeleton
- Event bus and dependency container abstractions
- ADR documentation for the architectural decisions

## Structure

- app/api: API routers and endpoints
- app/application: use cases and application services
- app/domain: business entities and domain rules
- app/infrastructure: integrations and external service implementations
- app/core: configuration, logging, middleware, responses, security, and tracing
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
