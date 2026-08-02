# Reference Data Strategy

This document defines the global reference data model for BUILD.
Reference data is shared platform-wide and is not owned by any single tenant or catalogue.

## Purpose

- Establish a global vocabulary for BUILD
- Avoid duplicate definitions across tenants and contexts
- Ensure consistent meaning for AI, assessment, content, and catalogue services
- Separate reference concepts from tenant-specific academic data

## What is reference data?

Reference data includes stable domain concepts that are reused across the platform.
It is authoritative, globally scoped, and typically managed by platform governance.

Examples:

- Difficulty Levels
- Bloom Taxonomy Levels
- Question Types
- Languages
- Citation Styles
- Content Licenses
- Media Types
- File Types
- AI Models / Embedding Providers
- Credit Units
- Academic Calendars
- Degree Types
- Countries

## Ownership

Reference data is owned by a platform-level bounded context, not by a tenant.
This context provides common concepts to:

- `Catalogue`
- `Academic Content`
- `AI Service`
- `CBT`
- `Reporting`

## Principles

- Reference data should be immutable or versioned when meaning changes.
- Reference data may be extended, but additions must preserve compatibility.
- Tenants may map local values to global reference IDs, but they may not redefine the reference concept.
- Reference data is the source of truth for shared taxonomies, not tenant-specific configuration.

## Example reference entities

- `DifficultyLevel`
- `BloomTaxonomyLevel`
- `QuestionType`
- `Language`
- `CitationStyle`
- `ContentLicense`
- `MediaType`
- `FileType`
- `AIModel`
- `EmbeddingProvider`
- `DegreeType`
- `AcademicCalendar`
- `CreditUnit`

## Use cases

- A course maps its credit units to a global `CreditUnit` reference.
- A topic or question maps its difficulty to a global `DifficultyLevel`.
- Content assets declare a `ContentLicense` and `MediaType`.
- The AI service resolves `Language` and `EmbeddingProvider` semantics consistently.

## Future direction

Reference data may become its own bounded context with dedicated APIs and governance.
This document is the strategic definition that should guide that future separation.
