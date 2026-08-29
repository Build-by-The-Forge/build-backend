# Assessment Core Design

## Purpose

Assessment Core delivers catalogue-defined academic content to learners and records measurable learning activity. It sits after Catalogue and before analytics and AI integrations.

```text
Identity -> Tenant -> Catalogue -> Assessment -> Attempt -> Analytics
                                      |
                                      v
                                      AI integrations
```

Catalogue remains authoritative for academic structure. Assessment Core owns questions, assessment assembly, delivery, submissions, and grading.

## Context boundaries

### Catalogue

Owns:

- Course
- Topic
- LearningOutcome
- CurriculumVersion

Answers: "What should be taught?"

### Assessment context

Owns:

- Question
- QuestionBank
- Assessment
- Attempt
- Answer and grading records

Answers: "How is learning assessed and what happened during an attempt?"

### AI and analytics

Consume published assessment and learning events. They do not directly mutate authoritative catalogue or assessment state without an authorized application workflow.

## Aggregate model

```text
QuestionBank
  +-- Question
        +-- QuestionOption

Assessment
  +-- AssessmentQuestion

Attempt
  +-- AttemptAnswer
```

### Question

Initial fields:

- `id`
- `tenant_id`
- `topic_id`
- optional `learning_outcome_id`
- `question_type`
- `prompt`
- `explanation`
- `difficulty`
- `marks`
- `status`
- timestamps

A Question owns its options. The first implementation supports MCQ questions with exactly one correct option.

### QuestionBank

A tenant-scoped collection used for authoring and organization. It references questions rather than duplicating their content.

### Assessment aggregate

Initial fields:

- `id`
- `tenant_id`
- title
- instructions
- duration
- availability window
- status
- scoring policy
- assessment questions

### AssessmentQuestion

An owned assessment item containing:

- source question ID
- prompt snapshot
- option snapshots
- display order
- marks
- catalogue references used for analytics

Snapshots are created before or during publication and are the source for student delivery.

### Attempt aggregate

An attempt belongs to one student, assessment, and tenant. It owns answer records, submission state, score, and grading metadata.

## State machines

### Assessment

```text
DRAFT
  -> PUBLISHED
  -> OPEN
  -> CLOSED
  -> ARCHIVED
```

Only valid domain transitions are allowed. Publication freezes the assessment question snapshots.

### Attempt

```text
NOT_STARTED
  -> IN_PROGRESS
  -> SUBMITTED
  -> GRADED
```

An attempt cannot be submitted twice. Submitted answers and their question snapshots remain stable for grading and audit.

## Security flow

Every protected operation follows:

```text
Bearer token
  -> AuthenticatedPrincipal
    -> X-Tenant-Slug
      -> active membership
        -> required permission
          -> tenant-scoped application command
            -> tenant-scoped repository
```

The client cannot choose the authoritative tenant ID. Catalogue relationships must be validated in the selected tenant before a question is created.

Recommended failure semantics:

- `401` for authentication failures
- `400` for missing tenant selection
- `403` for missing membership or permission
- `404` for resources unavailable in the current tenant
- `422` for invalid question or assessment data

## Initial authorization matrix

| Capability | Student | Lecturer | Faculty admin | Admin/owner |
| --- | ---: | ---: | ---: | ---: |
| Read published assessments | Yes | Yes | Yes | Yes |
| Create/update questions | No | Yes | Yes | Yes |
| Archive questions | No | No | Yes | Yes |
| Create assessments | No | Yes | Yes | Yes |
| Publish assessments | No | No | Yes | Yes |
| Start attempts | Yes | Optional | Optional | Optional |
| Submit own attempts | Yes | Optional | Optional | Optional |
| Read own results | Yes | No | No | No |
| Read tenant results | No | Scoped | Yes | Yes |

The permission vocabulary should be added incrementally as each capability is implemented.

## Scoring

The first release uses deterministic MCQ scoring:

```text
question_score = marks if selected_option.is_correct else 0
assessment_score = sum(question_scores)
percentage = assessment_score / total_marks * 100
```

The submitted answer stores the selected option and the question snapshot used for grading. Future scoring strategies must not reinterpret historical attempts silently.

## Event contracts

Initial events:

- `question.created`
- `question.updated`
- `question.archived`
- `assessment.created`
- `assessment.published`
- `assessment.closed`
- `attempt.started`
- `attempt.submitted`
- `attempt.graded`

Each event should include:

- event name and version
- aggregate ID
- tenant ID
- actor ID where applicable
- occurred-at timestamp
- minimal state-change payload

Events should be idempotent for downstream consumers.

## Implementation sequence

1. Add Question and QuestionOption domain models.
2. Add catalogue relationship validation.
3. Add question repository, mapper, Unit of Work, and migrations.
4. Add question authoring commands and APIs.
5. Add tenant and authorization integration tests.
6. Add QuestionBank.
7. Add Assessment draft and question selection.
8. Add publication snapshots.
9. Add attempt start and delivery.
10. Add submission and deterministic grading.
11. Add result access and assessment events.

Each step should be completed as a vertical slice before the next begins.

## Deliberately deferred

- Essay and subjective grading
- AI-generated questions
- Adaptive testing
- Randomized pools
- Partial credit
- Proctoring
- External AI calls during grading
- Advanced analytics
- Cross-tenant reporting

## Definition of done for v0.7.0

- MCQ question authoring works for authorized tenant members.
- Questions can reference valid same-tenant catalogue entities.
- Published assessments deliver immutable question snapshots.
- Students can start and submit one attempt according to assessment rules.
- MCQ attempts are automatically graded.
- Students can read their own results.
- Authorized staff can read appropriately scoped tenant results.
- Domain events are emitted for meaningful lifecycle transitions.
- Tenant isolation and authorization are covered by integration tests.
- The complete regression suite passes.
