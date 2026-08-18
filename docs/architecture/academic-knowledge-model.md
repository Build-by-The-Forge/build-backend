# Academic Knowledge Model

This document defines the canonical BUILD v0.4.0 academic catalogue architecture and the core bounded-context decisions for the catalogue.

## Purpose

The Academic Catalogue bounded context is the canonical source of truth for "what should be taught."
It must stay separate from learning content, media, and assessment artifacts.

This document is intended to lock down:
- aggregate boundaries,
- domain responsibilities,
- schema structure,
- stable public identifiers,
- API shape guidance,
- the delivery roadmap for v0.4.0.

## Bounded Context Map

The catalogue is one bounded context in a larger BUILD backend architecture.

```
                    BUILD Backend

                  ┌──────────────┐
                  │   Identity   │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │    Tenant    │
                  └──────┬───────┘
                         │
                         ▼
                 ┌────────────────┐
                 │   Catalogue    │
                 └──────┬─────────┘
                        │
                        ▼
                 ┌────────────────┐
                 │ AcademicContent│
                 └──────┬─────────┘
                        │
                        ▼
                 ┌────────────────┐
                 │   AI Service   │
                 └──────┬─────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
     Read Mode                  CBT Engine
```

This map explains the flow of responsibility and the intended separation between the canonical academic catalogue, learning content, and AI-powered experiences.

## 1. Bounded Context

### Catalogue Context

The catalogue answers:

> What is the academic offering and how is it structured over time?

It does NOT answer:

> What learning materials should students consume?

That belongs to a separate `Content` bounded context.

### Core catalogue aggregates

- `Course`
- `CurriculumVersion`
- `Topic`
- `LearningOutcome`
- `Prerequisite`
- `CourseOffering`
- `ReferenceMaterial`

Each aggregate has a distinct responsibility.

## 2. Aggregate responsibilities

### Aggregate ownership

Each aggregate in the academic catalogue has a single owner.

- `Faculty` → `Tenant`
- `Department` → `Tenant`
- `Programme` → `Tenant`
- `Course` → `Catalogue`
- `Topic` → `Catalogue`
- `CurriculumVersion` → `Catalogue`
- `LearningOutcome` → `Catalogue`
- `Prerequisite` → `Catalogue`
- `CourseOffering` → `Catalogue`
- `ReferenceMaterial` → `Catalogue`
- `Book` → `AcademicContent`
- `PDF` → `AcademicContent`
- `Chunk` → `AcademicContent`
- `Embedding` → `AI Service`
- `Question` → `CBT`
- `Attempt` → `CBT`

This avoids duplicated responsibility and keeps Catalogue focused on the academic truth rather than learning assets.

### Course

A permanent academic identity owned by a department.
It describes the unit of instruction, not the session delivery.

Key responsibilities:
- canonical course code and title
- credit units
- level and semester classification
- department ownership
- course type / catalog status

Example:

- `CSC201`
- `Algorithms and Data Structures`
- `3 Units`
- `100` level
- `core`

### CurriculumVersion

A versioned programme syllabus.

Why this matters:
- curricula change over time,
- topics and learning outcomes belong to the curriculum version,
- the same course can appear differently in different versions.

Key responsibilities:
- programme-specific effective syllabus snapshot
- active / archived lifecycle
- association to admission session(s)

Example:

- `BSc Computer Science 2025`
- version `2025-1`
- effective during `2025/2026`

### Topic

A topic lives under a `CurriculumVersion` and a course.
It is the primary content unit for AI, CBT, and analytics.

Key responsibilities:
- curriculum-specific topic structure
- slugs for stable public references
- hierarchical or sequence ordering

Example:

- `Graph Traversal`
- `Sorting`
- `Dynamic Programming`

### LearningOutcome

A syllabus objective attached to a topic.
These become AI objectives, CBT objectives, and analytics targets.

Example:

- explain recursion
- implement DFS
- analyze complexity

### Prerequisite

A relationship between courses.
This is a first-class link, not a free-text property.

Key responsibilities:
- self-referential course dependency
- type: prerequisite / co-requisite
- status and archival

### CourseOffering

A session-specific offering for a course.
This changes every academic session, unlike the course itself.

Key responsibilities:
- academic session / semester
- delivery details such as instructor, capacity, modality
- offering lifecycle

Example:

- `CSC201 Fall 2025`
- `Dr. Adebayo`
- `capacity 500`

### ReferenceMaterial

Metadata about recommended or required materials.
The actual file content or learning asset belongs in the `Content` context.

Key responsibilities:
- title, authors, edition, publisher, type
- recommended vs required flag
- open access / external link metadata

Example:

- `Introduction to Algorithms, 4th Edition`
- `ISBN`
- `Required`

## 3. Catalogue vs Content separation

### Information lifecycle

This is how information should flow through BUILD:

```
NUC CCMAS
      │
      ▼
Curriculum Import
      │
      ▼
Catalogue
      │
      ▼
Academic Content
      │
      ▼
OCR
      │
      ▼
Cleaning
      │
      ▼
Chunking
      │
      ▼
Embeddings
      │
      ▼
AI
      │
      ▼
Read Mode / CBT
```

The Catalogue captures the academic truth. Academic Content captures the actual study materials. AI stitches them together.

### Catalogue answers

- what courses exist?
- what does the curriculum require?
- what topics and outcomes are official?
- which programmes consume which courses?

### Content answers

- what resources are recommended?
- which chapters, videos, and PDF pages matter?
- how do we render a lesson or reading unit?
- how do we build CBT questions and learning paths?

This separation keeps the catalogue stable while content evolves.

## 4. Recommended canonical schema

### Core tables

- `courses`
- `curriculum_versions`
- `curriculum_courses`
- `curriculum_topics`
- `learning_outcomes`
- `course_prerequisites`
- `course_offerings`
- `reference_materials`
- `course_reference_materials` (optional)

### Normalized shape

`courses`
- internal UUID primary key
- department_id
- code (public canonical course code)
- title
- credit_units
- level
- semester
- type
- status
- description
- created_at / updated_at

`curriculum_versions`
- UUID
- programme_id
- name
- version
- effective_session_id
- expires_session_id
- status
- created_at / updated_at

`curriculum_courses`
- UUID
- curriculum_version_id
- course_id
- year_level
- semester_number
- sequence
- category
- status
- created_at / updated_at

`curriculum_topics`
- UUID
- curriculum_course_id
- title
- slug
- description
- level
- sequence
- status
- created_at / updated_at

`learning_outcomes`
- UUID
- curriculum_topic_id
- sequence
- description
- status
- created_at / updated_at

`course_prerequisites`
- UUID
- course_id
- prerequisite_course_id
- required_type
- status
- created_at / updated_at

`course_offerings`
- UUID
- course_id
- academic_session_id
- semester_number
- instructor
- capacity
- modality
- status
- created_at / updated_at

`reference_materials`
- UUID
- title
- authors
- publisher
- edition
- isbn
- material_type
- url
- recommended
- required
- open_access
- status
- created_at / updated_at

`course_reference_materials`
- UUID
- course_id
- reference_material_id
- status
- created_at / updated_at

## 5. Stable identifiers

Every entity in the system should define two identifiers:

- `Internal ID` → UUID for persistence and joins
- `Public ID` → stable external identifier for URLs, APIs, and imports

### Examples

| Entity | Internal ID | Public ID |
|---|---|---|
| Course | UUID | `CSC201` |
| Programme | UUID | `btech-csc` |
| Department | UUID | `csc` |
| Faculty | UUID | `soc` |
| Topic | UUID | `graph-traversal` |
| CurriculumVersion | UUID | `csc-2025` |

### Rules

- `Course.code` is the canonical public identifier for courses.
- `Topic.slug` is the canonical public identifier for topics.
- `CurriculumVersion.version` or slug should be a stable public identifier.
- `Programme.slug`, `Department.slug`, and `Faculty.slug` are public identifiers.

Do not expose raw database primary keys as the main public contract unless required for join or internal routing.

## 6. API design guidance

### Example read endpoints

- `GET /catalogue/courses`
- `GET /catalogue/courses/{code}`
- `GET /catalogue/programmes/{slug}/curriculums`
- `GET /catalogue/curriculums/{id}/topics`
- `GET /catalogue/topics/{slug}`
- `GET /catalogue/courses/{code}/prerequisites`

### Filtering and list queries

- by `department_id` or `department_slug`
- by `programme_slug`
- by `curriculum_version`
- by `academic_session`
- by `status`

### Validation

- course code format
- topic slug format
- curriculum version lifecycle rules
- prerequisite relationship consistency

## 6. Versioning

Curricula evolve over time. The catalogue should model that as a new version, not as mutation of existing records.

For example:

```
CSC201

↓

Curriculum v2025

↓

Topics
```

Later:

```
CSC201

↓

Curriculum v2030

↓

Updated Topics
```

This keeps historical student data valid and preserves the syllabus snapshot that was in force at admission.

## 7. Development roadmap for v0.4.0

### Phase 4.1 — Catalogue architecture finalized
- final aggregate boundaries
- schema contract
- stable external identifiers
- interface decisions for APIs and services

### Phase 4.2 — Domain entities implemented
- `Course`
- `CurriculumVersion`
- `Topic`
- `LearningOutcome`
- `Prerequisite`
- `CourseOffering`
- `ReferenceMaterial`

### Phase 4.3 — SQLAlchemy models + mappers
- aligned with canonical schema
- preserving public identifiers
- minimizing denormalization

### Phase 4.4 — Alembic migrations
- generate schema after architecture approval
- preserve rollback safety

### Phase 4.5 — Repository implementations
- query responsibilities for course/catalogue data
- support programme and curriculum lookups

### Phase 4.6 — Application services & UoW
- orchestrate catalogue commands and queries
- isolate DB session handling

### Phase 4.7 — API endpoints
- read-only catalogue surface for v0.4.0
- start with `GET` operations and filters

### Phase 4.8 — Seeder enrichment
- add core course catalogue sample data
- keep topics and outcomes optional for first pass

### Phase 4.9 — Tests
- domain tests
- repository tests
- API tests
- integration tests

### Phase 4.10 — CI, documentation, release tag
- update docs
- add release notes
- tag v0.4.0

## 8. Recommended next step

Create a single canonical design artifact before further code:

- `docs/architecture/academic-knowledge-model.md`

This document should be the contract for the catalogue module and the foundation for all subsequent work in v0.4.0.

Once agreed, implementation can proceed against a stable model instead of refactoring later.
