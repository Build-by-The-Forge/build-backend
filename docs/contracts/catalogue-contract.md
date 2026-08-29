# Catalogue Contract

## Ownership

- Catalogue owns academic truth.
- It is the source of truth for courses, curricula, topics, learning outcomes, prerequisites, course offerings, and reference metadata.

## Public IDs

- `Course.code` is the canonical public identifier for courses.
- `Topic.slug` is the canonical public identifier for topics.
- `CurriculumVersion.version` or slug is the stable public identifier for curriculum versions.
- `Programme.slug`, `Department.slug`, `Faculty.slug` are public identifiers.

## APIs

Stable catalogue APIs should expose read operations first:
- `GET /catalogue/courses`
- `GET /catalogue/courses/{code}`
- `GET /catalogue/programmes/{slug}/curriculums`
- `GET /catalogue/curriculums/{id}/topics`
- `GET /catalogue/topics/{slug}`

## Events

Catalogue publishes events when academic truth changes, for example:
- `course.created`
- `course.updated`
- `curriculum_version.created`
- `topic.created`
- `learning_outcome.created`

## Service boundaries

- The catalogue service owns data modeling and persistence for academic entities.
- Academic Content may reference catalogue IDs but does not own catalogue entities.
- AI services may consume catalogue data for semantic retrieval, but may not mutate catalogue truth directly.
