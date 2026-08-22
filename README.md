# BUILD Backend

Backend platform for BUILD, a multi-tenant academic catalogue and CBT foundation.

BUILD is a security-first modular monolith. Its current focus is tenant-owned academic knowledge: courses, topics, learning outcomes, and reference materials protected by authentication, membership, and permission checks.

## Status

Current development line: `feat/catalogue-learning-outcomes`

Implemented foundation:

- FastAPI application, health endpoints, request IDs, and security headers
- Async SQLAlchemy persistence with PostgreSQL support
- SQLite test environment and Alembic migrations
- Identity registration, authentication, sessions, refresh, logout, and password reset
- Argon2 password hashing and token services
- Authenticated principal resolution
- Tenant and membership persistence with explicit `X-Tenant-Slug` context
- Role-based catalogue authorization
- Tenant-scoped course reads, creation, updates, publishing, and archiving
- Tenant-scoped Topic, LearningOutcome, and ReferenceMaterial management
- Domain events, in-process event bus, metrics, and tracing hooks
- Domain, repository, API, tenancy, authorization, and regression tests

The repository is private and under active development. API contracts may evolve before the first stable release.

## Architecture

```text
HTTP API
   |
   v
Authentication -> AuthenticatedPrincipal
   |
   v
Tenant context -> Membership -> Permission
   |
   v
Application command/query
   |
   v
Domain aggregate and invariants
   |
   v
Repository -> Unit of Work -> Database
```

| Layer | Responsibility |
| --- | --- |
| `app/api` | FastAPI routes, request schemas, response envelopes, dependency declarations |
| `app/application` | Commands, handlers, and use-case services |
| `app/domain` | Aggregates, value objects, invariants, and domain events |
| `app/infrastructure` | ORM models, repositories, mappers, security adapters, and UoWs |
| `app/core` | Configuration, authorization, dependencies, middleware, telemetry, and responses |
| `app/bootstrap` | Runtime service wiring and dependency container |
| `alembic` | Database migration history |
| `tests` | Domain, API, repository, tenancy, authorization, and regression tests |

### Catalogue ownership

```text
Tenant
  Faculty
    Department
      Course
        Topic
          LearningOutcome
        ReferenceMaterial
```

Child resources are resolved through their parent chain and active tenant. Clients never provide the authoritative tenant ID for protected operations.

## Security Model

Protected requests follow this sequence:

1. `Authorization: Bearer <access-token>` authenticates the user.
2. `X-Tenant-Slug: <tenant-slug>` selects the requested context.
3. The backend verifies that the tenant exists and is active.
4. An active membership is resolved for the authenticated user.
5. The membership role is checked against the required permission.
6. Repository queries apply tenant filters at the database boundary.

### Status conventions

- `401`: missing or invalid credentials, or unknown user
- `400`: required tenant selector is missing
- `403`: membership or permission is insufficient
- `404`: resource is not visible in the current tenant context
- `422`: request validation failed

### Current tenant roles

| Role | Catalogue capabilities |
| --- | --- |
| `student` | Read catalogue |
| `lecturer` | Read, create, and update catalogue content |
| `hod` | Read, create, and update catalogue content |
| `faculty_admin` | Read, create, update, publish, and archive |
| `admin` / `owner` | All current catalogue permissions |

Permission policy is defined in `app/core/authorization.py`, and routes declare requirements with `require_permission(...)`.

## API Surface

Successful and handled error responses use this envelope:

```json
{
  "success": true,
  "data": {},
  "meta": {},
  "request_id": "..."
}
```

### Health and platform

```text
GET /
GET /metrics
GET /health/live
GET /health/ready
GET /health/startup
```

### Identity

```text
POST /identity/users
POST /identity/authenticate
POST /identity/refresh
POST /identity/logout
POST /identity/forgot-password
POST /identity/reset-password
GET  /identity/me
GET  /identity/whoami
GET  /identity/tenant-context
GET  /identity/permissions
GET  /identity/authorization-probe
```

### Courses

Protected catalogue routes require a bearer token and `X-Tenant-Slug`.

```text
GET   /catalogue/courses/
GET   /catalogue/courses/{course_id}
POST  /catalogue/courses/
PATCH /catalogue/courses/{course_id}
POST  /catalogue/courses/{course_id}/publish
POST  /catalogue/courses/{course_id}/archive
```

Course creation derives ownership from tenant context. `tenant_id` is rejected in the request body.

### Topics

```text
POST  /catalogue/courses/{course_id}/topics
GET   /catalogue/courses/{course_id}/topics
PATCH /catalogue/topics/{topic_id}
POST  /catalogue/topics/{topic_id}/archive
```

### Learning outcomes

```text
POST  /catalogue/topics/{topic_id}/learning-outcomes
GET   /catalogue/topics/{topic_id}/learning-outcomes
PATCH /catalogue/learning-outcomes/{learning_outcome_id}
POST  /catalogue/learning-outcomes/{learning_outcome_id}/archive
```

### Reference materials

```text
POST  /catalogue/topics/{topic_id}/reference-materials
GET   /catalogue/topics/{topic_id}/reference-materials
PATCH /catalogue/reference-materials/{reference_material_id}
POST  /catalogue/reference-materials/{reference_material_id}/archive
```

Reference materials are currently persisted as course-owned children. Nested topic routes verify that the topic belongs to the tenant-scoped course. A future schema decision may add direct topic ownership.

## Local Development

### Requirements

- Python `3.12+`
- PostgreSQL for non-testing environments
- Redis for Redis-backed integrations
- Docker Desktop for Compose workflows

### Setup

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS/WSL:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Install development tools with:

```bash
pip install -e ".[dev]"
```

### Configuration

Configuration uses environment variables and an optional `.env` file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | `development`, `testing`, `staging`, or `production` |
| `POSTGRES_URL` | empty outside testing | Async SQLAlchemy database URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `DEBUG` | `false` | Debug configuration flag |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Request timeout setting |
| `TENANT_HEADER` | `x-tenant-id` | Configured setting; catalogue context currently uses `X-Tenant-Slug` |

Example:

```dotenv
APP_ENVIRONMENT=development
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/build
REDIS_URL=redis://localhost:6379/0
```

### Run the API

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. Interactive API documentation is available at `/docs` and `/redoc`.

### Migrations

```bash
alembic upgrade head
```

Create a migration after reviewing model changes:

```bash
alembic revision --autogenerate -m "describe the schema change"
```

Review autogenerated migrations manually, especially tenant constraints, foreign keys, indexes, and SQLite batch operations.

## Docker Compose

```bash
docker compose up --build
```

Stop services with:

```bash
docker compose down
```

| Service | Address |
| --- | --- |
| API | `http://localhost:8000` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Compose credentials are for local development only.

## Testing and Quality

Run all tests:

```bash
python -m pytest -q
```

Run focused suites:

```bash
python -m pytest tests/domain/catalogue -q
python -m pytest tests/integration/catalogue -q
```

Compile modules:

```bash
python -m compileall -q app tests
```

Run linting and type checking when installed:

```bash
ruff check app tests
mypy app
```

Pytest sets `APP_ENVIRONMENT=testing` and uses in-memory SQLite. API integration tests seed the application engine explicitly; repository tests may use a separate fixture engine.

## Project Layout

```text
app/
├── api/                  # HTTP routes and schemas
├── application/          # Commands, handlers, and services
├── bootstrap/            # Dependency container and runtime wiring
├── core/                 # Config, policies, dependencies, middleware
├── db/                   # SQLAlchemy base, engine, and sessions
├── domain/               # Aggregates, value objects, and domain rules
├── events/               # Domain events and event bus
├── infrastructure/       # ORM models, mappers, repositories, adapters
├── integrations/         # External integration boundaries
├── middleware/           # Middleware boundaries
├── telemetry/            # Telemetry boundaries
└── workers/              # Background worker boundaries

alembic/                  # Migration scripts
docs/                     # Architecture, ADRs, and specifications
scripts/                  # Seed and maintenance scripts
tests/                    # Domain, integration, and foundation tests
```

## Engineering Conventions

- Keep business invariants in domain aggregates and value objects.
- Keep authentication and authorization at application boundaries.
- Resolve tenant ownership from trusted context, never request payloads.
- Apply tenant filters in repository queries, not only in Python.
- Treat academic records as stateful entities; prefer archive transitions to hard deletion.
- Eager-load async SQLAlchemy relationships before mapping to domain objects.
- Emit domain events for meaningful state changes.
- Add focused tests for every security and persistence boundary.
- AI and ingestion workflows must propose changes through an authorized, auditable workflow rather than silently mutating authoritative data.

## Roadmap

### Catalogue

- Catalogue hardening and response-contract cleanup
- Topic-level reference ownership review
- Curriculum versions and reproducible academic state
- Course prerequisites and offerings
- Academic structure APIs for faculties, departments, programmes, levels, sessions, and semesters

### CBT platform

- Question bank and question versions
- Assessment blueprints
- Attempts, submissions, scoring, and results
- Student enrolment, progress, and learning history

### Intelligence

- Source and document provenance
- Institutional change proposals and verification workflows
- Search, embeddings, and retrieval-augmented generation
- Curriculum intelligence and academic knowledge graph
- Evidence-backed FUTA News capability

### Production hardening

- Audit logs and durable event delivery
- Rate limiting, caching, and background queues
- Stronger token and key configuration
- Observability dashboards and alerting
- Deployment automation and operational runbooks

## Related Documentation

- [Architecture](docs/architecture.md)
- [Academic knowledge model](docs/architecture/academic-knowledge-model.md)
- [Academic catalogue specification](docs/architecture/academic-catalogue-specification.md)
- [Architecture decision records](docs/architecture/adr/)
- [Catalogue event contracts](docs/events/catalogue-events.md)
- [Module template](docs/module-template.md)

## License

Private repository. All rights reserved.
