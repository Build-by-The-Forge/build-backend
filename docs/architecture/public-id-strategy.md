# Public ID Strategy

This document defines the stable public identifier strategy for BUILD entities.
Public IDs are the external handles used by APIs, contracts, and integrations.
They must be stable, opaque, and never derived from internal database integers.

## Purpose

- Prevent leaking database internals
- Enable safe external references across services
- Support deterministic entity migration and auditability
- Make identifiers friendly for AI prompts and traceability

## Format

Public IDs should use a prefixed namespace and a stable encoded token.
Common format:

```text
{entity}_{unique}
```

Example prefixes:

- `course_`
- `topic_`
- `objective_`
- `reference_`
- `content_`
- `question_`
- `attempt_`
- `curriculum_`
- `programme_`
- `faculty_`
- `department_`
- `tenant_`

Example IDs:

- `course_01JYQFZ6FX4W9Z0Q2N3M1K5HVH`
- `topic_01JYQK4ERK9GS8D3Z0C7T4U1V2`
- `content_01JYQK8J6B7PW2F9X0L4D3S5A1`
- `question_01JYQKL3Q1F8D6B2P7N9R4V0M`

## Requirements

- Each entity type owns its own prefix.
- Public IDs are used externally in APIs, events, audit logs, and integrations.
- Internal persistence may still use UUIDs, surrogate keys, or natural keys.
- Public IDs are not mutable once assigned.
- Public IDs should be generated at the moment the entity is created.

## Generation guidelines

- Prefer collision-resistant identifiers such as ULIDs, KSUIDs, or UUIDv7.
- Keep the prefix constant and use the encoded token for uniqueness.
- Avoid exposing sequential numeric values.
- Use the same generation strategy across bounded contexts.

## Usage boundaries

- APIs should accept public IDs in request paths and responses.
- Events should carry public IDs for referenced entities.
- Contracts should document the public ID format for each shared entity.
- Internal services may map public IDs to internal IDs at the boundary.

## Examples by domain

### Academic Catalogue

- `course_{id}`
- `curriculum_{id}`
- `topic_{id}`
- `objective_{id}`
- `reference_{id}`

### Content

- `content_{id}`
- `asset_{id}`
- `chunk_{id}`

### AI / Assessment

- `embedding_{id}`
- `question_{id}`
- `attempt_{id}`
- `response_{id}`

## Principle

Never expose raw database integers as external identifiers.
Public IDs are the contract-level identity for BUILD entities.
