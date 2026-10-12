# BUILD Backend

Backend platform for BUILD, a multi-tenant academic catalogue and CBT foundation.

BUILD is a security-first modular monolith. Its current focus is tenant-owned academic knowledge: courses, topics, learning outcomes, and reference materials protected by authentication, membership, and permission checks.

## Status

Current development line: `feat/assessment-engine`

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
- Question authoring with MCQ validation and draft/published/archived lifecycle
- Assessment definitions with tenant-scoped question snapshots and lifecycle rules
- Assessment application and HTTP APIs
- Attempt lifecycle with learner ownership, resume behavior, and submission
- Snapshot-based question delivery that excludes answer keys
- Attempt answer persistence with snapshot question identity and selected option indexes
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

### Assessment flow

```text
Assessment
   |
   +--> published question snapshots
   |
   +--> Attempt -> submitted
             |
             +--> snapshot question delivery
```

Assessment attempts are tenant- and learner-scoped. Delivery reads the immutable
`assessment_questions` snapshot rows rather than mutable live Question records.
Scoring, results, timers, and AI integration are intentionally deferred.

Current assessment-engine checkpoint:

```text
Assessment definition         complete
Assessment application        complete
Assessment API                complete
Attempt lifecycle             complete
Attempt persistence           complete
Attempt application           complete
Attempt API                   complete
Snapshot question delivery    complete
Attempt answer persistence    complete
Deterministic scoring         next
```

### Phase 3D — Attempt answer persistence

Phase `3D: Attempt Answer Persistence` records the learner's selected option against the immutable assessment snapshot without making grading decisions.

Core rules:

- Persist learner selections against snapshot question records, not live question records.
- Treat `3D` as a persistence and interaction layer, not a scoring layer.
- Enforce one answer per `attempt_id + assessment_question_id` pair.
- Scope answers to the active tenant and authenticated learner.
- Reject answers for questions that are not part of the current attempt's assessment.
- Validate the selected option against the snapshot options list.
- Prevent mutation of answers after the attempt has been submitted.
- Never expose correctness metadata such as `is_correct`, `answer_key`, or `score` in 3D responses.

Recommended API surface:

```text
PUT    /assessment/attempts/{attempt_id}/answers/{question_id}
GET    /assessment/attempts/{attempt_id}/answers
DELETE /assessment/attempts/{attempt_id}/answers/{question_id}
```

The current implementation stores `selected_option_index`. Correctness, scoring, and results belong to later phases (`3F+`).

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

> Current implementation note: the tenant selector header is `X-Tenant-Slug` in the API contract, and the runtime dependency layer reads the lowercase header value `x-tenant-slug` when building the tenant context.

### Current tenant roles

| Role | Catalogue capabilities |
| --- | --- |
| `student` | Read catalogue and published assessments; start, resume, and submit own attempts |
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

### Questions

```text
POST  /assessment/questions
GET   /assessment/questions/{question_id}
PATCH /assessment/questions/{question_id}
POST  /assessment/questions/{question_id}/publish
POST  /assessment/questions/{question_id}/archive
```

Question creation is tenant-scoped and validates its catalogue relationships. MCQ
questions require at least two options and exactly one correct option.

### Assessments

```text
POST  /assessment/assessments
GET   /assessment/assessments
GET   /assessment/assessments/{assessment_id}
PATCH /assessment/assessments/{assessment_id}
POST  /assessment/assessments/{assessment_id}/publish
POST  /assessment/assessments/{assessment_id}/questions
```

Assessments must contain at least one question before publication. Published
assessments cannot receive additional questions.

### Attempts and question delivery

```text
POST /assessment/assessments/{assessment_id}/attempts
GET  /assessment/attempts/{attempt_id}
GET  /assessment/attempts
POST /assessment/attempts/{attempt_id}/submit
GET  /assessment/attempts/{attempt_id}/questions
```

Attempt start, retrieval, listing, submission, and question delivery are scoped
to the authenticated learner and selected tenant. Starting an assessment resumes
an existing active attempt. The question-delivery response contains prompt,
option text, position, sequence, and marks, but never correctness metadata.

### Attempt answers

```text
PUT    /assessment/attempts/{attempt_id}/answers/{assessment_question_id}
GET    /assessment/attempts/{attempt_id}/answers
DELETE /assessment/attempts/{attempt_id}/answers/{assessment_question_id}
```

Save requests use `selected_option_index` and are idempotent for a given attempt
and snapshot question. Only persisted answers are returned. Answer mutations are
allowed while an attempt is in progress and rejected after submission; answer
responses never include correctness or grading metadata.

## Local Development

### Requirements

- Python `3.12+` (CI and the image use 3.13)
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

`requirements.txt` holds the runtime dependencies. For tests, linting and
pre-commit, install the development set instead (it includes the runtime
set):

```bash
pip install -r requirements-dev.txt
```

Both files pin every package, including indirect ones, to an exact version;
`tests/test_dependency_declarations.py` fails if your environment differs
from them. The project itself is not installed: run commands from the
repository root.

### Configuration

Configuration uses environment variables and an optional `.env` file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | `development`, `testing`, `staging`, or `production` |
| `POSTGRES_URL` | empty outside testing | Async SQLAlchemy database URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `DEBUG` | `false` | Debug configuration flag |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Request timeout setting |

Example:

```dotenv
APP_ENVIRONMENT=development
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/build
REDIS_URL=redis://localhost:6379/0
```

In testing mode, the app uses an in-memory SQLite database automatically via `APP_ENVIRONMENT=testing`; this keeps the test suite isolated from PostgreSQL.

### Run the API

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. Interactive API documentation is available at `/docs` and `/redoc`.

The app initializes the database on startup when `APP_ENVIRONMENT` is not set to `production` and will create the schema automatically for the configured database.

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
python -m pytest tests/domain/assessment -q
python -m pytest tests/integration/assessment -q
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
- Attempt answer persistence (3D) with one answer per question per attempt
- Submission hardening and immutable submitted attempts
- Deterministic scoring and results
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
- [Assessment Core design](docs/architecture/assessment-core.md)
- [Architecture decision records](docs/adr/)
- [Assessment Core ADR](docs/adr/007-assessment-core.md)
- [Catalogue event contracts](docs/events/catalogue-events.md)
- [Module template](docs/module-template.md)

## License

Private repository. All rights reserved.
