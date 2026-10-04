# BUILD Phase 1 — Foundation & Production Boundary

**Status:** In execution — Milestone 1 complete
**Repositories:** `build-backend`, `ai-service`
**Target:** Move the backend + AI-service foundation from the current state to a production-capable architectural baseline.
**Governing documents:** `docs/BUILD_MASTER_PRD.md` (target state); this plan (execution contract)

> **Revision note.** This document contains the original Phase 1 plan (§1–§18) followed by **Revision 1 — Decisions after Milestone 1** (§19–§24). Where they differ, **Revision 1 governs**. In particular, the revised milestone sequence in §22 supersedes the original milestone list in §14.

---

## 1. Phase Objective

Phase 1 establishes the production foundation required before implementing the deeper academic intelligence layer.

The primary objective is:

> **Make `build-backend` the authoritative system of record for identity, tenants, memberships, authorization, and academic/business state, while making `ai-service` a properly authenticated, tenant-aware intelligence service that owns only AI-specific state and capabilities.**

At the end of Phase 1:

* backend identity is authoritative;
* tenant context is authoritative;
* AI-service no longer relies on its legacy identity/domain model;
* service-to-service authentication is enforced;
* authorization boundaries are explicit;
* tenant isolation is enforced end-to-end;
* production secrets/configuration are safe;
* authentication and authorization behavior is tested;
* AI-service can operate against the backend-owned identity/domain without shadow tables;
* deployment and migration behavior are deterministic;
* the foundation is ready for Phase 2 Academic Core implementation.

---

## 2. Phase 1 Scope

Phase 1 consists of seven workstreams.

| Workstream | Area                                          | Primary repo |
| ---------- | --------------------------------------------- | ------------ |
| 1          | Identity & authentication boundary            | Backend + AI |
| 2          | Tenant context & multi-tenancy                | Backend + AI |
| 3          | Authorization & permissions                   | Backend      |
| 4          | AI-service legacy-domain removal              | AI           |
| 5          | Service-to-service security                   | Backend + AI |
| 6          | Production configuration & security hardening | Both         |
| 7          | Verification, integration & production gates  | Both         |

---

## 3. Workstream 1 — Identity & Authentication Boundary

### Objective

Establish the backend as the authoritative identity provider for BUILD application users.

#### Backend responsibilities

The backend owns:

* user accounts;
* authentication;
* password credentials;
* sessions/tokens;
* password reset;
* account lifecycle;
* account status;
* organization memberships;
* authentication-related audit events.

#### AI-service responsibilities

AI-service must **not** maintain an independent application identity system.

It may maintain AI-specific session/operational state, but it must receive authenticated identity context from the backend.

### 3.1 Audit Current Authentication

Before changing implementation:

* inspect backend authentication endpoints;
* inspect JWT/session implementation;
* inspect password hashing;
* inspect token validation;
* inspect authentication dependencies;
* inspect current tests;
* inspect AI-service login routes;
* inspect AI-service identity models;
* inspect every AI route that obtains `user_id`;
* inspect every AI route that accepts caller-supplied identity fields.

#### Required output

Produce an explicit identity flow:

```text
Client
  ↓
Backend authentication
  ↓
Authenticated user
  ↓
Tenant/membership context
  ↓
Authorized AI-service request
  ↓
AI-service trusted context
```

Do not implement until the existing flow has been mapped.

---

## 4. Workstream 2 — Tenant Context & Multi-Tenancy

### Objective

Make tenant identity explicit and trustworthy throughout the request lifecycle.

The authoritative tenant identifier is the backend tenant identity.

AI-service must never derive tenant identity from:

* arbitrary request body fields;
* arbitrary headers supplied by an untrusted client;
* legacy `school_id`;
* AI-local user records.

### 4.1 Define Canonical Request Context

The authenticated context should conceptually contain:

```text
user_id
tenant_id
membership_id
role
permissions
correlation_id
```

Only the fields actually required by a service should be propagated.

### 4.2 Backend Context

Backend must determine:

```text
authenticated user
        ↓
active organization/tenant
        ↓
membership
        ↓
role
        ↓
permissions
```

The client must not be allowed to arbitrarily select a tenant to which it has no membership.

### 4.3 AI Context

AI-service receives trusted context from the backend.

The AI layer uses that context for:

* memory;
* document processing;
* retrieval;
* RAG;
* agent execution;
* AI sessions;
* usage accounting;
* audit events.

The existing `tenant_id` memory implementation should transition from the temporary bridge to the canonical backend tenant UUID.

### 4.4 Tenant Isolation Tests

Explicitly test:

* Tenant A cannot retrieve Tenant B's memory.
* Tenant A cannot retrieve Tenant B's documents.
* Tenant A cannot access Tenant B's retrieval metadata.
* Tenant A cannot invoke Tenant B's AI session.
* Tenant A cannot mutate Tenant B's AI state.
* Missing tenant context is rejected.
* Invalid tenant context is rejected.
* Unauthorized membership is rejected.

Tenant isolation must be tested at the service boundary, not merely at the API endpoint.

---

## 5. Workstream 3 — Authorization & Permission Model

### Objective

Implement the PRD's organization-scoped authorization model.

The conceptual authorization model is:

```text
Account
   ↓
Organization/Tenant
   ↓
Membership
   ↓
Role
   ↓
Scope
   ↓
Permissions
```

The initial role model includes:

* Student
* Lecturer/Contributor
* Academic Administrator
* Owner/Tenant Administrator

### 5.1 Backend Authorization

Define and enforce permissions for:

#### Student

* read permitted academic content;
* use CBT;
* access own progress;
* use AI features;
* access own learning data.

#### Lecturer/Contributor

* permitted academic contribution;
* content contribution;
* question contribution;
* scoped academic review where granted.

#### Academic Administrator

* curriculum/content administration;
* academic review;
* publication workflows;
* academic configuration.

#### Owner/Tenant Administrator

* tenant administration;
* membership administration;
* tenant configuration;
* permitted administrative operations.

### 5.2 Permission Categories

Use the PRD's permission concepts where applicable:

```text
READ
WRITE
SENSITIVE_WRITE
ADMIN
ACADEMIC_REVIEW
OWNER
```

Sensitive operations must require explicit authorization.

### 5.3 Authorization Tests

Test:

* authenticated but unauthorized;
* correct role;
* incorrect role;
* correct tenant;
* wrong tenant;
* correct scope;
* insufficient scope;
* sensitive mutation without permission;
* administrative operation without permission;
* cross-tenant access.

Do not rely solely on frontend role checks.

---

## 6. Workstream 4 — Remove AI-Service Legacy Domain

This is the immediate continuation of Item 2.

### Objective

Remove runtime dependency on the old AI-service identity/exam domain.

The following are no longer valid AI-service system-of-record domains:

```text
schools
users
exams
exam_sessions
answer_sheets
```

Their migrations have already been removed.

Now their **runtime usage** must be removed or replaced.

### 6.1 Inventory Legacy Runtime Dependencies

Search all AI-service code for:

```text
school_id
School
User
Exam
ExamSession
AnswerSheet
schools
exams
exam_sessions
answer_sheets
```

Classify every occurrence:

```text
REMOVE
REPLACE WITH BACKEND CONTEXT
REMODEL AS AI DOMAIN
TEST FIXTURE ONLY
DOCUMENTATION ONLY
```

Do not blindly delete them.

### 6.2 Identity Routes

The existing AI-service login/identity implementation must be evaluated.

Where AI-service currently performs application authentication:

```text
Client → AI-service login
```

the target becomes:

```text
Client
  ↓
Backend authentication
  ↓
Backend-authorized AI request
  ↓
AI-service
```

AI-service may authenticate **services**, but it should not become a competing user-authentication authority.

### 6.3 Exam Runtime

Determine which existing exam functionality belongs in:

```text
build-backend
```

versus:

```text
ai-service
```

The target architecture is:

#### Backend

Owns:

* questions;
* assessments;
* attempts;
* answers;
* scores;
* CBT lifecycle;
* publication;
* verification state.

#### AI-service

Provides intelligence such as:

* question generation;
* question evaluation;
* explanation generation;
* difficulty analysis;
* curriculum alignment;
* question-quality evaluation.

AI-service should not own the authoritative exam lifecycle.

---

## 7. Workstream 5 — Service-to-Service Security

### Objective

Establish authenticated backend ↔ AI-service communication.

The architecture becomes:

```text
React Native
     │
     ▼
build-backend
     │
     │ authenticated service request
     ▼
ai-service
     │
     ▼
Model Gateway
```

The mobile client must not directly impersonate the backend when calling privileged AI operations.

### 7.1 Service Authentication

Implement a production-safe mechanism for backend → AI-service authentication.

Requirements:

* strong service credentials;
* secret rotation capability;
* no hard-coded secrets;
* environment/configuration based secrets;
* request authentication;
* timestamp/replay protection where appropriate;
* correlation IDs;
* tenant context;
* user context;
* authorization context.

### 7.2 Request Integrity

AI requests should carry enough information to establish:

```text
Who?
Which tenant?
What operation?
Which request?
Which correlation?
Which authorization?
```

The AI-service must reject:

* missing authentication;
* invalid credentials;
* malformed context;
* unauthorized operations;
* invalid tenant context;
* replayed/expired requests where applicable.

---

## 8. Workstream 6 — Production Security & Configuration

### Objective

Remove unsafe development defaults before production implementation expands.

### 8.1 Secrets

Audit:

* JWT secrets;
* service credentials;
* database credentials;
* Redis credentials;
* model provider keys;
* encryption keys;
* webhook secrets;
* callback secrets.

No production secret should have a repository/default fallback.

### 8.2 Configuration Validation

Applications should fail clearly when required production configuration is absent.

Examples:

```text
DATABASE_URL
REDIS_URL
JWT_SECRET
AI_SERVICE_URL
SERVICE_AUTH_SECRET
MODEL_PROVIDER
MODEL_NAME
MODEL_API_KEY
```

Development defaults should not silently become production credentials.

### 8.3 Rate Limiting

Verify and wire rate limiting where required.

Prioritize:

* authentication;
* password reset;
* AI requests;
* expensive processing;
* uploads;
* administrative mutations.

### 8.4 Security Headers & Transport

Verify:

* HTTPS expectations;
* CORS;
* trusted origins;
* security headers;
* request size limits;
* upload limits;
* timeout configuration;
* proxy behavior.

---

## 9. Workstream 7 — Production Verification

No Phase 1 workstream is complete merely because its implementation exists.

Every workstream requires:

```text
Inspect
  ↓
Implement
  ↓
Unit tests
  ↓
Integration tests
  ↓
Negative/security tests
  ↓
Fresh environment verification
  ↓
Review diff
  ↓
Commit
```

---

## 10. Required Integration Test Environment

The final Phase 1 verification environment should contain:

```text
PostgreSQL 17
Redis 8
build-backend
ai-service
```

From a clean database:

```text
backend migrations
        ↓
backend schema
        ↓
AI migrations
        ↓
AI schema
        ↓
application startup
        ↓
authenticated request
        ↓
AI operation
        ↓
AI state persisted
```

Verify independently that:

* backend schema remains intact;
* AI schema remains isolated;
* both migration version tables coexist;
* no legacy AI tables are recreated;
* tenant context survives the entire request;
* authentication survives the service boundary;
* authorization survives the service boundary.

---

## 11. Required Test Matrix

### Authentication

* valid credentials;
* invalid credentials;
* expired token;
* malformed token;
* revoked/invalid session where applicable;
* password reset;
* account disabled.

### Authorization

* Student;
* Contributor;
* Academic Administrator;
* Owner;
* insufficient permissions;
* wrong tenant;
* wrong scope.

### Tenant isolation

* same tenant;
* different tenant;
* missing tenant;
* forged tenant;
* invalid membership.

### AI-service

* authenticated request;
* unauthenticated request;
* invalid service credential;
* invalid context;
* unauthorized AI operation;
* valid memory read/write;
* cross-tenant memory attempt.

### Database

* fresh backend migration;
* fresh AI migration;
* both version tables;
* no legacy tables;
* backend schema unchanged;
* AI tables present;
* application startup.

### Security

* secret validation;
* rate limiting;
* request size limits;
* timeout behavior;
* replay/expiry protections;
* audit logging.

---

## 12. Production Readiness Gate

Phase 1 is **NOT COMPLETE** until all of the following are true.

### Architecture

* [ ] Backend is authoritative for identity.
* [ ] Backend is authoritative for tenant/membership state.
* [ ] Backend is authoritative for academic/business state.
* [ ] AI-service is an intelligence layer, not a shadow backend.
* [ ] Ownership boundaries are documented.

### Identity

* [ ] Backend authentication is production-safe.
* [ ] Password handling is production-safe.
* [ ] Token/session validation is production-safe.
* [ ] Password reset is production-safe.
* [ ] AI-service no longer authenticates application users independently.

### Tenancy

* [ ] Tenant context is canonical.
* [ ] Tenant context cannot be forged by clients.
* [ ] AI-service is tenant-aware.
* [ ] Cross-tenant reads are blocked.
* [ ] Cross-tenant writes are blocked.

### Authorization

* [ ] Roles are defined.
* [ ] Permissions are enforced server-side.
* [ ] Sensitive operations require appropriate authorization.
* [ ] Negative authorization tests exist.

### AI-service

* [ ] Legacy identity dependencies removed.
* [ ] Legacy exam-domain runtime dependencies removed/replaced.
* [ ] AI-owned persistence remains isolated.
* [ ] AI-service receives trusted identity/tenant context.
* [ ] Memory operates on canonical tenant IDs.

### Service security

* [ ] Backend → AI-service authentication implemented.
* [ ] Service secrets are externally configured.
* [ ] Request integrity is protected.
* [ ] Correlation IDs work end-to-end.
* [ ] Unauthorized service requests are rejected.

### Configuration/security

* [ ] Production secrets have no unsafe defaults.
* [ ] Required configuration is validated.
* [ ] Rate limiting is operational.
* [ ] Upload/request limits are enforced.
* [ ] CORS/security configuration is explicit.

### Verification

* [ ] Fresh PostgreSQL 17 passes migrations.
* [ ] Fresh Redis 8 passes relevant integration tests.
* [ ] Backend tests pass.
* [ ] AI-service tests pass except explicitly documented pre-existing/environment-specific failures.
* [ ] Security tests pass.
* [ ] Cross-service integration tests pass.
* [ ] Production startup path passes.
* [ ] Working trees are clean.
* [ ] Every change is committed narrowly.

---

## 13. Explicitly Out of Scope

To prevent Phase 1 from becoming another uncontrolled mega-phase, do **not** implement the following here unless required as a direct dependency:

* full curriculum ingestion;
* full Read Mode;
* Video Mode;
* advanced CBT features;
* production vector search;
* complete RAG;
* AI Tutor;
* adaptive learning;
* study plans;
* campus map;
* social/group system;
* leaderboard;
* subscriptions;
* advanced analytics;
* full agent ecosystem;
* model evaluation laboratory.

Those belong to later phases.

---

## 14. Phase 1 Milestones (original — superseded by §22)

### Milestone 1 — Identity Audit

**Deliverable:** authoritative identity architecture and legacy dependency map.

### Milestone 2 — Backend Authentication

**Deliverable:** production-safe backend identity/authentication.

### Milestone 3 — Tenant Context

**Deliverable:** canonical tenant/membership context throughout backend and AI requests.

### Milestone 4 — Authorization

**Deliverable:** server-side role/scope/permission enforcement.

### Milestone 5 — AI Legacy Removal

**Deliverable:** AI-service no longer depends on legacy users/schools/exams domain.

### Milestone 6 — Service Security

**Deliverable:** authenticated backend → AI-service communication.

### Milestone 7 — Security Hardening

**Deliverable:** production configuration, secrets, rate limits and security boundaries.

### Milestone 8 — End-to-End Verification

**Deliverable:** clean PostgreSQL/Redis environment with authenticated, authorized, tenant-isolated backend → AI-service flow.

---

## 15. Commit Discipline

Phase 1 must preserve the same discipline used during Item 2.

Commits should be narrow and independently reviewable.

Examples:

```text
fix(backend): harden authentication flow
test(backend): add authorization boundary coverage
feat(backend): establish canonical tenant context
refactor(ai-service): remove legacy identity dependency
feat(ai-service): consume trusted tenant context
feat(backend): authenticate ai-service requests
feat(ai-service): validate service requests
fix(ai-service): remove legacy exam runtime dependency
security(backend): harden production configuration
security(ai-service): validate production configuration
test: add backend-ai tenant isolation integration coverage
```

Avoid:

```text
feat: finish phase 1
```

with hundreds of unrelated changes.

---

## 16. Phase 1 Success Definition

At the end of Phase 1, a request should conceptually travel through the system like this:

```text
┌──────────────────┐
│   React Native   │
└────────┬─────────┘
         │
         │ user authentication
         ▼
┌──────────────────────────────┐
│       build-backend          │
│                              │
│  Identity                    │
│  Tenant                      │
│  Membership                  │
│  Authorization               │
│  Academic/business state     │
└────────────┬─────────────────┘
             │
             │ authenticated + authorized
             │ tenant + user context
             ▼
┌──────────────────────────────┐
│         ai-service           │
│                              │
│  RAG                         │
│  OCR                         │
│  Memory                      │
│  Agents                      │
│  Generation                  │
│  Model Gateway               │
│  AI processing               │
└────────────┬─────────────────┘
             │
             ▼
      ┌──────────────┐
      │ Model Provider│
      └──────────────┘
```

The fundamental rule is:

> **The backend decides who the user is, which tenant they belong to, and what they are allowed to do. AI-service decides how intelligence is produced within that authorized context.**

That boundary becomes the foundation on which the rest of the BUILD PRD can safely be implemented.

---

## 17. Expected Phase 1 Outcome

If executed correctly, Phase 1 should move the combined platform approximately from:

**~33–37% implementation**

to roughly:

**~40–45% implementation**,

while potentially moving the **production-readiness baseline from ~20–25% toward ~35–45%**.

The exact percentage should be recalculated after Phase 1 from an explicit PRD requirement matrix rather than estimated from commit count.

---

## 18. Execution Rule

For every Phase 1 task, use this sequence:

**Inspect → Map → Design → Implement → Test → Attack the boundary → Verify against fresh infrastructure → Review diff → Commit → Stop.**

Do not start the next milestone merely because the code compiles.

A milestone is complete only when its **behavior, security boundary, tests, and production assumptions have been verified**.

---

# Revision 1 — Decisions after Milestone 1

Milestone 1 (`docs/phase1-m1-identity-audit.md`; commits `36b8f48` ai-service, `6603f31` backend) found that the backend's tenancy and authorization design is sound but its authentication is a placeholder (plaintext password storage, forgeable unsigned tokens, reset tokens returned in responses), that no tenant/membership provisioning path exists, and that the backend ↔ AI-service channel cannot authenticate in either direction even though both test suites pass. The decisions below resolve the questions in §7 of that audit.

## 19. Decisions

### 19.1 AI-service user-facing routes

**Decision: AI-service does not authenticate end users independently.**

```text
React Native
     │
     │ access token
     ▼
build-backend
     │
     │ validates user
     │ resolves tenant
     │ resolves membership
     │ resolves permissions
     │
     │ signed service request
     ▼
ai-service
```

AI-service trusts **only authenticated backend-originated requests** for user-facing operations. These routes receive trusted identity context from the backend:

* chat
* explain
* generate-questions
* retrieve
* tree
* memory
* future agent endpoints

AI-service keeps its own **service authentication**, but not a second user login system. The legacy flow

```text
AI user → AI login → AI JWT → AI authorization
```

is removed.

### 19.2 Trusted context between backend → AI-service

**Decision: the context goes inside the signed HMAC material**, using a structured protocol that is formally specified before implementation.

Conceptual headers:

```text
X-BUILD-Timestamp
X-BUILD-Request-ID
X-BUILD-Signature
```

with the signature covering deterministic material such as:

```text
HTTP_METHOD
PATH
TIMESTAMP
REQUEST_ID
BODY_HASH
USER_ID
TENANT_ID
MEMBERSHIP_ID
```

The trusted context contains:

```text
user_id
tenant_id
membership_id
role
permissions
correlation_id
request_id
timestamp
```

**Do not blindly forward the entire permission set if it isn't necessary.** The backend remains the authorization authority:

```text
Backend:
"User X is authorized to invoke AI operation Y."

AI-service:
"Given this trusted context, execute Y within tenant T."
```

This prevents AI-service from becoming a second authorization system.

Field semantics:

* `tenant_id` is security-critical.
* `user_id` is security/audit-critical.
* `role` and `permissions` are authorization context.
* `correlation_id` / `request_id` are observability context.

### 19.3 HMAC scheme and secrets

**Decision: one protocol, separate secrets per direction.**

```text
BACKEND → AI
    backend_ai_hmac_secret

AI → BACKEND
    ai_backend_hmac_secret
```

not a single shared secret — a leaked secret must not let an attacker impersonate both services. The protocol is identical in both directions:

```text
timestamp
request_id
canonical_request
HMAC-SHA256
```

**The static Bearer fallback is removed.** There is one clearly defined service-authentication mechanism.

Replay protection: the HMAC includes a timestamp and request ID. Both services reject stale timestamps, malformed signatures, invalid signatures, and reused request IDs where replay protection is required, with a small clock-skew tolerance.

### 19.4 AI exam-generation and adaptive code

**Decision: AI intelligence stays in AI-service. Exam authority stays in the backend.** The AI generation logic is not moved wholesale into the backend.

```text
                    BUILD BACKEND
                         │
              owns authoritative state
                         │
          ┌──────────────┴──────────────┐
          │                             │
       Questions                     Attempts
       Assessments                   Answers
       Exams                         Scores
       Publication                   Results
          │
          │ AI request
          ▼
                    AI-SERVICE
                         │
             intelligence operations
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     Generation       Evaluation     Adaptation
          │              │              │
          └──────────────┼──────────────┘
                         │
                       LLM/RAG
```

Example:

* **Backend asks:** generate 20 questions for MEE101, Topic X, difficulty distribution Y, based on these authorized curriculum/document IDs.
* **AI-service returns:** generated questions, quality metadata, source references, difficulty estimates, generation metadata.
* **Backend decides:** whether they are accepted, whether they enter the question bank, whether they are published, which assessment uses them, how attempts are scored, and how results are persisted.

> **Backend owns truth. AI-service produces intelligence.**

An agent must never directly become the authoritative owner of academic state.

### 19.5 Tenant and membership provisioning

**Decision: Milestone 2**, as a major part of it. Authentication is not production-ready while there is no legitimate path for:

```text
User
 ↓
Tenant
 ↓
Membership
 ↓
Role
 ↓
Permissions
```

---

## 20. Locked architectural principle

> **BUILD has one identity authority, one tenant authority, and one academic/business authority: the backend.**

AI-service is an intelligence subsystem operating within trusted context, not a parallel application.

| Concern              | Owner      |
| -------------------- | ---------- |
| Identity             | Backend    |
| Authentication       | Backend    |
| Tenants              | Backend    |
| Memberships          | Backend    |
| Roles/permissions    | Backend    |
| Courses              | Backend    |
| Curriculum structure | Backend    |
| Questions            | Backend    |
| Assessments          | Backend    |
| Attempts             | Backend    |
| Scores/results       | Backend    |
| Documents            | AI-service |
| OCR                  | AI-service |
| Chunking             | AI-service |
| Embeddings           | AI-service |
| Retrieval            | AI-service |
| RAG                  | AI-service |
| AI generation        | AI-service |
| AI memory            | AI-service |
| Agents               | AI-service |
| Model orchestration  | AI-service |

> **AI can recommend, generate, analyze, explain and reason — but the backend decides what becomes authoritative platform state.**

---

## 21. Permanent lesson from Milestone 1

Both test suites were green while the real integration was broken, because each side mocked the other. From Milestone 3 onward, the backend ↔ AI-service boundary is verified by running **the real services against each other**, not only mocks.

---

## 22. Revised milestone sequence (supersedes §14)

### M1 — Identity Audit ✅

Complete. No code changes; architecture and vulnerability discovery.

```text
36b8f48  ai-service
6603f31  backend
```

### M2 — Production Identity + Tenant Provisioning

#### Authentication

* real Argon2id password hashing;
* signed access tokens;
* expiry;
* refresh/session strategy;
* secure password reset;
* account lifecycle;
* authentication tests.

#### Tenant provisioning

Define how the first tenant gets created. For BUILD today:

```text
BUILD
 └── FUTA tenant
```

but the data model must support

```text
University A
 ├── Faculties
 ├── Departments
 ├── Users
 └── Memberships

University B
 ├── Faculties
 ├── Departments
 ├── Users
 └── Memberships
```

without redesigning the identity system later.

#### Membership provisioning

Establish legitimate mechanisms for:

* Owner creation;
* admin invitation;
* lecturer/contributor invitation;
* student onboarding;
* membership acceptance;
* role assignment;
* membership revocation;
* tenant switching where a user belongs to multiple organizations.

### M3 — Backend → AI Security Boundary

After M2 provides real identity:

```text
User
 ↓
Backend authentication
 ↓
Tenant + membership
 ↓
Authorization
 ↓
Signed AI request
 ↓
AI-service
```

Implement:

* directional HMAC;
* canonical signing;
* timestamp;
* request ID;
* body hash;
* trusted context;
* replay protection;
* service authentication;
* removal of static Bearer fallback.

Then test the **real services against each other**, not mocks (§21).

### M4 — AI-Service Legacy Removal & Domain Boundary

Investigate and eliminate:

```text
AI users
AI schools
AI login
AI JWT
AI exam ownership
AI-local tenant assumptions
integer school_id
```

Then establish backend-owned:

```text
users
tenants
memberships
courses
questions
assessments
attempts
answers
results
```

and AI-owned:

```text
learning_memory
session_memory
documents
chunks
embeddings
retrieval state
AI sessions
agent state
AI processing metadata
```

with the exact ownership refined against the PRD/database implementation.

### M5 — AI Intelligence Contract

Only after the security boundary works, formalize the AI API contracts that become the foundation for Read Mode explanations, RAG, document ingestion, question generation, question evaluation, summarization, conversational tutoring, memory, and future agent orchestration. For example:

```text
POST /internal/v1/generation/questions
POST /internal/v1/generation/explanation
POST /internal/v1/retrieval/search
POST /internal/v1/memory/query
POST /internal/v1/memory/upsert
POST /internal/v1/chat
```

These are **internal service contracts**, not a second public application backend.

### M6 — Production Integration & Security Gate

```text
Fresh PostgreSQL 17
Fresh Redis 8
        │
        ▼
Backend migration
        │
        ▼
AI migration
        │
        ▼
Backend startup
        │
        ▼
AI startup
        │
        ▼
Create tenant
        │
        ▼
Create user
        │
        ▼
Create membership
        │
        ▼
Authenticate
        │
        ▼
Call AI
        │
        ▼
Signed request
        │
        ▼
AI validates context
        │
        ▼
AI operation
        │
        ▼
Tenant-scoped persistence
        │
        ▼
Backend receives result
```

Then deliberately attack it — every one of these must fail appropriately:

```text
forged user
forged tenant
forged role
forged signature
expired timestamp
replayed request
wrong service secret
cross-tenant memory
unauthenticated AI request
direct AI login
```

---

## 23. Workstream coverage of the revised milestones

The workstreams in §3–§9 still apply; the revised milestones regroup them:

| Revised milestone | Workstreams |
|---|---|
| M2 | 1 (identity), 2 (tenant/membership provisioning) |
| M3 | 5 (service security), 2 (trusted tenant context across the boundary) |
| M4 | 4 (legacy removal) |
| M5 | 2, 3 (AI operations within authorized context) |
| M6 | 7 (verification), 6 (production configuration/security) |

Workstream 3 (authorization) applies throughout; the AI-related permissions gap (audit B-8) is addressed where AI operations are authorized by the backend.

## 24. Execution rule (unchanged)

**Inspect → Map → Design → Implement → Test → Attack the boundary → Verify against fresh infrastructure → Review diff → Commit → Stop.**
