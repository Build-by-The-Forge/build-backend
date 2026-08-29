# ADR 007: Assessment Core Architecture

## Status

Accepted

## Date

2026-08-22

## Context

BUILD's catalogue bounded context defines the academic structure that should be taught:

```text
Course -> Topic -> LearningOutcome
```

The next bounded context must deliver that structure to learners, record attempts, grade submissions, and preserve the historical state used to produce results.

The assessment system must remain tenant-aware and must not allow later edits to change the meaning of a previously published assessment or completed attempt.

## Decision

BUILD will implement Assessment Core as a separate bounded context with independent aggregate boundaries:

```text
QuestionBank
  Question
    QuestionOption

Assessment
  AssessmentQuestion

Attempt
  AttemptAnswer
```

The first release will support multiple-choice questions with one correct option, fixed marks, automatic grading, and tenant-scoped student attempts.

### Aggregate boundaries

- `QuestionBank` owns question membership and ordering.
- `Question` owns its options and authoring lifecycle.
- `Assessment` owns its selected assessment-question snapshots and publication lifecycle.
- `Attempt` owns submitted answer snapshots and grading state.

`AssessmentQuestion` and `AttemptAnswer` are owned entities. They are not exposed as independent aggregate roots.

### Tenant ownership

Tenant ownership is derived from the authenticated request:

```text
AuthenticatedPrincipal
  -> TenantContext
    -> Permission
      -> Application command
        -> Tenant-scoped repository
```

Client-provided `tenant_id` values are never authoritative. Question, assessment, and attempt lookups must be tenant-scoped at the repository boundary.

Catalogue relationships are validated through tenant-scoped parent references. A question cannot reference a topic or learning outcome from another tenant.

### Publication snapshots

Publishing an assessment creates an immutable snapshot for each selected question:

- question ID
- prompt text
- option text and display order
- marks
- question type
- learning outcome reference when available

Student delivery reads the snapshot, not mutable authoring records. Later question edits cannot change an already published assessment or a completed attempt.

### Lifecycles

Assessment lifecycle:

```text
DRAFT -> PUBLISHED -> OPEN -> CLOSED -> ARCHIVED
```

Attempt lifecycle:

```text
NOT_STARTED -> IN_PROGRESS -> SUBMITTED -> GRADED
```

Invalid transitions are rejected by the domain model. Submitted attempts are immutable except for controlled grading metadata.

### Authorization

Authorization remains capability-based and builds on the existing tenant permission system. Initial capabilities include:

- question read/create/update/archive
- question-bank read/manage
- assessment read/create/update/publish/archive
- attempt start/submit
- own-result read
- tenant-result read

Students may deliver published assessments, submit their own attempts, and read their own results. They cannot author questions or publish assessments.

### Events

Assessment Core will emit stable domain events for meaningful transitions:

- `question.created`
- `question.updated`
- `question.archived`
- `assessment.created`
- `assessment.published`
- `assessment.closed`
- `attempt.started`
- `attempt.submitted`
- `attempt.graded`

Events include the aggregate ID, tenant ID, actor ID where applicable, occurred-at timestamp, and event version.

## Alternatives considered

### One aggregate for all assessment data

Rejected. A single aggregate would couple question authoring, assessment publication, student delivery, submission, and grading. It would also create unnecessary transaction contention and make historical snapshots harder to reason about.

### Resolve tenant from request body

Rejected. Request payloads are untrusted and would create a direct tenant-isolation vulnerability.

### Resolve tenant from JWT only

Rejected. A user may belong to multiple tenants. Tenant selection must remain explicit and membership must be verified for each request.

### Deliver live question records after publication

Rejected. Authoring edits would change historical assessments and make completed results non-reproducible.

### Begin with AI-generated questions

Rejected. AI integration should consume stable question, assessment, and grading contracts. AI may propose content later, but it must not bypass authorization or publication workflows.

## Consequences

### Positive

- Clear separation between catalogue truth and assessment delivery
- Tenant isolation is consistent with the existing backend security chain
- Historical assessments and results are reproducible
- Question authoring can evolve without changing completed attempts
- Domain events provide a future integration point for analytics and AI

### Negative

- Publication requires snapshot storage and additional persistence
- More aggregate boundaries require explicit application workflows
- Question and assessment updates need careful lifecycle tests
- Initial schema design must account for future question types without overbuilding them

## Implementation constraints

- Use the existing API, application, domain, infrastructure, repository, and Unit of Work conventions.
- Preserve the catalogue as the source of academic structure.
- Keep the first implementation limited to MCQ, one correct answer, fixed marks, automatic grading, and basic availability.
- Prefer archive transitions over hard deletion.
- Add domain, repository, API, authorization, tenant-isolation, and integration tests for each slice.
- Do not modify catalogue behavior as part of Assessment Core unless an explicit cross-context contract requires it.
