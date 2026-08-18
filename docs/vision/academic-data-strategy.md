# Academic Data Strategy

This document defines the source hierarchy for academic knowledge in BUILD, the platform principles that govern curriculum truth, and the reference data scope that supports future AI-native education services.

## Purpose

The Academic Data Strategy is the constitution for BUILD's academic intelligence layer.
It answers:

- Where does every piece of academic knowledge come from?
- Which sources are allowed to define curriculum?
- What belongs in Catalogue versus Content?
- What is reference data versus tenant data?

## Source hierarchy

BUILD treats academic truth as a layered hierarchy of authority.
Higher layers may define or approve the curriculum; lower layers may interpret, annotate, or supplement it.

1. `NUC CCMAS` and national curriculum policy
2. `FUTA Senate` approved programmes and regulations
3. Faculty curriculum committees and programme approvals
4. Department programme handbooks and course blueprints
5. Official textbook and publisher curriculum specifications
6. Official course definitions, topics, and learning outcomes in the `Academic Catalogue`
7. Academic content assets mapped to catalogue entities
8. AI-generated explanations and pedagogy
9. Student-generated notes and derivative study artifacts

## Principles

- Curriculum truth is authoritative, versioned, and auditable.
- Only designated academic authorities may change the catalogue definition.
- Learning content and AI artifacts may reference catalogue truth, but they cannot override it.
- Uploaded files may enrich content, but they do not redefine curriculum.
- Reference data is global and platform-owned, not tenant-specific.

## What is curriculum truth?

Curriculum truth in BUILD is the official description of:

- programmes and degree pathways
- course definitions and credit units
- curriculum versions and effective sessions
- course topics and learning outcomes
- prerequisite relationships
- course offerings and delivery metadata

These definitions are owned by the `Academic Catalogue` bounded context.

## What is not curriculum truth?

The following are explicitly not sources of curriculum truth:

- user-uploaded PDFs, slides, or notes
- AI-generated explanations or summaries
- student submissions or notes
- unofficial department documents not approved by faculty governance
- transient content chunks or embeddings

Uploaded files are supplementary content only.

## Reference data

Some data should be modeled as global reference entities rather than tenant data.
Reference data is shared across BUILD and used by catalogue, content, AI, and assessment services.

Examples:

- Countries
- Languages
- Degree types
- Academic calendars
- Credit units
- Bloom taxonomy levels
- Difficulty levels
- Question types
- Content licenses
- Citation styles

Reference data exists to reduce duplication, normalize meaning, and make AI reasoning consistent.

## AI and academic truth

AI is a reasoning layer, not an owner of curriculum.

- AI may generate study help, explanations, and retrieval results.
- AI outputs are derived from catalogue metadata and content embeddings.
- AI must respect the catalogue as the canonical syllabus authority.
- AI should flag uncertain or unsupported claims when the source of truth is not clear.

## Governance and future-proofing

- Curriculum changes must be recorded with effective dates and version identifiers.
- The platform should maintain an audit trail for all catalogue updates.
- Public IDs should be used to reference entities externally, not raw database keys.
- The Academic Knowledge Platform should remain explicit about what it owns versus what it references.

## Suggested document links

- `docs/domain-map.md` — frozen domain model for BUILD v0.4.0
- `docs/decisions/001-source-of-truth.md` — the source-of-truth architectural decision record
- `docs/contracts/README.md` — contract guidance for bounded context communication
