# Academic Knowledge Domain Map

This document captures the canonical domain model for BUILD v0.4.0.
It is intended to be stable and agreed before significant implementation work begins.

## Purpose

The domain map defines the primary entities, ownership boundaries, and relationship flow for the Academic Knowledge Platform.
It also establishes the intent to use stable public identifiers for entities rather than exposing database integers.

## Domain model diagram

```
Tenant
  ├─ Faculty
  │   └─ Department
  │       └─ Programme
  │           └─ CurriculumVersion
  │               ├─ Course
  │               │    ├─ Topic
  │               │    │   ├─ LearningOutcome
  │               │    │   ├─ ReferenceMaterial
  │               │    │   └─ QuestionBlueprint
  │               │    └─ Prerequisite
  │               └─ CourseOffering
  │                   ├─ AcademicSession
  │                   ├─ InstructorAssignment
  │                   └─ DeliveryDetails
  │
  └─ ReferenceData
       ├─ DegreeType
       ├─ AcademicCalendar
       ├─ CreditUnit
       ├─ BloomTaxonomyLevel
       ├─ DifficultyLevel
       ├─ QuestionType
       ├─ Language
       ├─ Country
       ├─ ContentLicense
       └─ CitationStyle

ContentResource
  ├─ MediaAsset
  ├─ Document
  ├─ Video
  ├─ PDF
  └─ Chunk

Chunk
  └─ Embedding

AI Service
  ├─ SemanticIndex
  ├─ RetrievalResult
  └─ Explanation

Assessment
  ├─ Question
  ├─ Attempt
  ├─ Response
  └─ Progress

```

## Core entities

### Tenant

Institutional structure is tenant-scoped. Tenants own faculties, departments, and programmes.

### Faculty

A faculty is a top-level academic division owned by a tenant.

### Department

A department owns programmes and course definitions.

### Programme

A programme defines a degree pathway and contains curriculum versions.

### CurriculumVersion

A versioned syllabus that expresses how a programme is delivered in a specific academic cycle.
Topics, learning outcomes, and course offerings are tied to a curriculum version.

### Course

A permanent academic unit of instruction.
Courses are defined once and referenced by curriculum versions.

### Topic

A curriculum topic belongs to a course and a curriculum version.
Topics are the primary unit for AI understanding, content mapping, and assessment blueprints.

### LearningOutcome

A measurable objective attached to a topic.
Learning outcomes are used by AI, assessment, and analytics.

### ReferenceMaterial

Metadata for recommended or required academic resources.
These are catalogue-owned references, while the actual resource asset belongs to the Content context.

### CourseOffering

A session-specific instantiation of a course.
It includes academic session, semester, instructor, modality, and capacity.

### ContentResource

Content assets are separate from the catalogue.
This entity lives in the Content context and is mapped back to catalogue topics and courses.

### Chunk and Embedding

Chunks are content fragments extracted from documents or media.
Embeddings are AI artifacts derived from chunks and used by the AI Service.

### QuestionBlueprint

Defines the assessment intent for a topic or learning outcome.
It is the bridge to CBT-style question generation.

### Assessment / Attempt / Progress

These entities belong to the CBT and progress monitoring contexts.
They consume catalogue structure and AI models but do not redefine curriculum truth.

## Public ID strategy

All domain entities should expose stable public IDs.
Database integers must never be used as external identifiers.

Examples:

- `course_01J...`
- `topic_01J...`
- `content_01J...`
- `question_01J...`
- `reference_01J...`
- `outcome_01J...`
- `curriculum_01J...`
- `attempt_01J...`

## Freeze criteria

The following entities should be agreed before implementing the v0.4 domain:

- `Tenant`
- `Faculty`
- `Department`
- `Programme`
- `CurriculumVersion`
- `Course`
- `Topic`
- `LearningOutcome`
- `Prerequisite`
- `ReferenceMaterial`
- `CourseOffering`
- `QuestionBlueprint`
- `ContentResource`
- `Chunk`
- `Embedding`
- `Question`
- `Attempt`
- `Progress`
- `ReferenceData`

Once this domain map is agreed, changes should be made only with an explicit architectural decision.
