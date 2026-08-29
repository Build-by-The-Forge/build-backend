# Versioning Strategy

This document defines the versioning strategy for BUILD artifacts and academic resources.
Versioning is essential for tracking changes, supporting rollback, and enabling AI reasoning over time.

## Purpose

- Distinguish canonical curriculum versions from content versions
- Provide stable naming for published academic artifacts
- Support evolution of AI prompts, references, and embeddings
- Clarify what changes require a new version versus a patch update

## Version categories

### Curriculum Version

A curriculum version represents an authoritative syllabus snapshot for a programme.
It is used by the Academic Catalogue as the unit of academic change.

Examples:

- `2025-1`
- `2026-2`
- `v2025.1`

Key properties:

- programme-specific
- effective date range
- published / archived status

### Content Version

Content version tracks a revision of learning material.
Content assets may be updated independently of curriculum versions.

Examples:

- `1.0.0`
- `2025.1`

### Topic Version

Topics may change over time when curriculum requirements evolve.
Topic versioning allows the platform to distinguish historical topic definitions.

### Reference Version

Reference materials and citations may be versioned separately.
This is important when sources are replaced, updated, or deprecated.

### Question Version

Question blueprints and assessment items should carry a version.
This enables reproducible assessment generation and audit trails.

### Embedding Version

Embeddings are AI artifacts that may be regenerated when models or chunking strategies change.
Embedding versioning ensures semantic search remains consistent and traceable.

### AI Prompt Version

AI prompts, templates, and generation strategies should be versioned.
When the AI context changes, the prompt version should increment so results can be audited.

## Versioning rules

- Use explicit version identifiers for published academic entities.
- Keep curriculum version separate from content and prompt versions.
- Increment a version when the meaning or output changes in a way that must be audited.
- Do not rely on timestamp-only versioning for canonical curriculum definitions.

## Recommended naming conventions

- `CurriculumVersion`: `YYYY-N` or `vYYYY.N`
- `ContentVersion`: `MAJOR.MINOR.PATCH`
- `TopicVersion`: `YYYY.N` or `vMAJOR.MINOR`
- `ReferenceVersion`: `YYYY.N` or `vMAJOR.MINOR`
- `QuestionVersion`: `MAJOR.MINOR`
- `EmbeddingVersion`: `model-{name}-{date}`
- `PromptVersion`: `prompt-{name}-v{number}`

## Lifecycle semantics

- `Draft` → not yet assigned a published curriculum version.
- `Published` → canonical and visible to downstream services.
- `Archived` → retained for historical reference but not active.

## Contract guidance

- API responses should include version identifiers for versioned entities.
- Events should carry relevant version metadata when publishing changes.
- Versioning should be part of the domain model, not only the persistence layer.
