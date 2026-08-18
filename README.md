# BUILD Backend

Backend service for the BUILD AI CBT Platform.

This repository implements the core backend of the BUILD platform using a modular monolith architecture built with FastAPI, SQLAlchemy Async, PostgreSQL, Redis, Alembic, and Docker.

---

## Current Version

**v0.4.0 — Academic Catalogue**

### Completed

- Platform Foundation
- Identity & Authentication
- JWT Authentication
- Password Hashing (Argon2)
- Refresh Token Rotation
- Password Reset Flow
- User Session Management
- SQLAlchemy Async Repository
- Unit of Work Pattern
- Dependency Injection Container
- Event Bus
- API Error Handling
- Request Context Middleware
- Security Headers
- Metrics & Tracing
- SQLite Test Environment
- Alembic Migrations
- Tenant Core / Multi-tenancy foundation
- Canonical FUTA curriculum seeding
- SQLite-safe `0004` batch migration for `faculty_id`
- Academic Catalogue specification drafted in `docs/`
- Automated Integration Tests

### In Progress

- Academic Catalogue bounded context
- Curriculum versioning
- Course / programme course model
- Topic-based learning structure
- Course prerequisites and learning outcomes
- Catalogue read APIs

---

## Tech Stack

- FastAPI
- SQLAlchemy 2.x (Async)
- PostgreSQL
- Redis
- Alembic
- Pydantic v2
- Pytest
- Docker Compose

---

## Project Structure

```
app/
├── api/
├── application/
├── bootstrap/
├── core/
├── db/
├── domain/
├── events/
└── infrastructure/

tests/
```

---

## Running Locally

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

Linux/macOS

```bash
source .venv/bin/activate
```

Windows

```powershell
.venv\Scripts\activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run the API

```bash
uvicorn app.main:app --reload
```

---

## Running Tests

```bash
pytest
```

or

```bash
pytest -v
```

---

## Docker

```bash
docker compose up --build
```

---

## Architecture

The backend follows a Domain-Driven Design inspired modular monolith.

Layers:

- Domain
- Application
- Infrastructure
- API
- Bootstrap
- Core

Persistence uses:

- SQLAlchemy Async
- Repository Pattern
- Unit of Work Pattern

---

## Roadmap

### ✅ v0.1.0

- Platform Foundation

### ✅ v0.2.0

- Identity & Access Management

### ✅ v0.3.0

- Tenant Core

### 🚧 Next

- Academic Catalogue implementation
- Course Management
- Curriculum Versioning
- Course Prerequisites
- Topic-Based Learning
- Question Bank
- CBT Engine
- AI Integration
- Study Analytics
- Notifications
- Progress Tracking
- Production Deployment

---

## License

Private repository.