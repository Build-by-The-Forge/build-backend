# Catalogue Event Catalog

This document catalogs events emitted by the Academic Catalogue and related bounded contexts.
Each event includes producer, consumer, payload shape, version guidance, and idempotency notes.

## Goals

- Make event semantics explicit before implementation
- Support future asynchronous integration with AI, content, and CBT services
- Capture naming, ownership, and consumer expectations

## Event conventions

- Event names are verbs in past tense or domain-specific nouns.
- Events carry public IDs for referenced entities.
- Payloads should be minimal and include version metadata when relevant.
- Events should be idempotent and publish state changes, not raw commands.
- Ordering should be maintained by the producer when required.

## Events

### CourseCreated

- Producer: Catalogue
- Consumer(s): Content, AI Service, CBT, Reporting
- Payload:
  - `course_id`
  - `public_id`
  - `tenant_id`
  - `department_id`
  - `title`
  - `code`
  - `credit_units`
  - `level`
  - `semester`
  - `status`
  - `created_at`
  - `version`
- Notes: idempotent if `course_id` already exists.

### CourseUpdated

- Producer: Catalogue
- Consumer(s): Content, AI Service, CBT, Reporting
- Payload:
  - `course_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`
- Notes: publish only meaningful field changes.

### CurriculumVersionPublished

- Producer: Catalogue
- Consumer(s): Content, AI Service, Reporting
- Payload:
  - `curriculum_version_id`
  - `public_id`
  - `programme_id`
  - `name`
  - `effective_session`
  - `status`
  - `published_at`
  - `version`
- Notes: ordering matters for curriculum timeline.

### TopicAdded

- Producer: Catalogue
- Consumer(s): Content, AI Service, CBT
- Payload:
  - `topic_id`
  - `public_id`
  - `course_id`
  - `curriculum_version_id`
  - `title`
  - `slug`
  - `sequence`
  - `created_at`
  - `version`

### TopicUpdated

- Producer: Catalogue
- Consumer(s): Content, AI Service, CBT
- Payload:
  - `topic_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`

### LearningOutcomeAdded

- Producer: Catalogue
- Consumer(s): AI Service, CBT, Reporting
- Payload:
  - `outcome_id`
  - `public_id`
  - `topic_id`
  - `description`
  - `created_at`
  - `version`

### LearningOutcomeUpdated

- Producer: Catalogue
- Consumer(s): AI Service, CBT, Reporting
- Payload:
  - `outcome_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`

### ReferenceMaterialAdded

- Producer: Catalogue
- Consumer(s): Content, AI Service, Reporting
- Payload:
  - `reference_id`
  - `public_id`
  - `course_id`
  - `topic_id`
  - `title`
  - `authors`
  - `publisher`
  - `isbn`
  - `reference_type`
  - `required`
  - `created_at`
  - `version`

### ReferenceMaterialUpdated

- Producer: Catalogue
- Consumer(s): Content, AI Service, Reporting
- Payload:
  - `reference_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`

### CourseOfferingCreated

- Producer: Catalogue
- Consumer(s): Content, AI Service, Reporting
- Payload:
  - `offering_id`
  - `public_id`
  - `course_id`
  - `curriculum_version_id`
  - `academic_session`
  - `semester`
  - `instructor_id`
  - `modality`
  - `capacity`
  - `created_at`
  - `version`

### CourseOfferingUpdated

- Producer: Catalogue
- Consumer(s): Content, AI Service, Reporting
- Payload:
  - `offering_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`

### QuestionBlueprintCreated

- Producer: Catalogue
- Consumer(s): CBT, AI Service, Reporting
- Payload:
  - `question_blueprint_id`
  - `public_id`
  - `topic_id`
  - `objective_id`
  - `question_type`
  - `difficulty_level`
  - `prompt_template`
  - `created_at`
  - `version`

### QuestionBlueprintUpdated

- Producer: Catalogue
- Consumer(s): CBT, AI Service, Reporting
- Payload:
  - `question_blueprint_id`
  - `public_id`
  - changed fields
  - `updated_at`
  - `version`

### ContentApproved

- Producer: Content
- Consumer(s): AI Service, Reporting
- Payload:
  - `content_id`
  - `public_id`
  - `approved_at`
  - `approved_by`
  - `version`

### EmbeddingGenerated

- Producer: AI Service
- Consumer(s): Retrieval, CBT, Reporting
- Payload:
  - `embedding_id`
  - `public_id`
  - `chunk_id`
  - `model_name`
  - `provider`
  - `created_at`
  - `version`
- Notes: idempotent for the same `chunk_id` and model combination.

### QuestionGenerated

- Producer: AI Service
- Consumer(s): CBT, Reporting
- Payload:
  - `question_id`
  - `public_id`
  - `blueprint_id`
  - `prompt_version`
  - `generated_at`
  - `metadata`
  - `version`

### ContentArchived

- Producer: Content
- Consumer(s): Reporting, AI Service
- Payload:
  - `content_id`
  - `public_id`
  - `archived_at`
  - `reason`
  - `version`

## Event catalog notes

- Producers should include event version metadata when the event schema changes.
- Consumers should treat events as idempotent and use entity public IDs to deduplicate.
- Ordering guarantees should be documented per topic when required.
- Event names and payloads should stay stable once the catalogue contract is agreed.
