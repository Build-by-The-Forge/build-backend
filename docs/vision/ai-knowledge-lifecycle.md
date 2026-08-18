# AI Knowledge Lifecycle

This document describes the AI knowledge lifecycle for BUILD.
It explains how curriculum, content, and AI artifacts flow from authoritative academic truth to student-facing experiences.

## Purpose

- Define the pipeline from curriculum to AI output
- Clarify ownership at each stage
- Make the AI service architecture repeatable and auditable
- Keep AI artifacts aligned with catalogue truth

## Lifecycle stages

1. `Curriculum`
   - The canonical academic syllabus owned by the `Academic Catalogue`.
2. `Topic`
   - The curriculum’s primary instructional units.
3. `Learning Objective`
   - Outcomes attached to topics.
4. `Reference`
   - Catalogue-referenced materials and metadata.
5. `Chunk`
   - Content fragments extracted from assets.
6. `Embedding`
   - Semantic vectors representing chunks.
7. `Retrieval`
   - Finding relevant chunks for a query.
8. `AI Context`
   - Assembled prompt state combining curriculum, topic, and retrieved content.
9. `Explanation`
   - AI-generated study help or explanation.
10. `Question Generation`
   - AI-generated assessment items.
11. `Validation`
   - Review and scoring logic for AI outputs.
12. `Publishing`
   - Making AI artifacts available to the student experience.
13. `Student`
   - Final consumption by a learner.

## Flow

```
Curriculum
   ↓
Topic
   ↓
Learning Objective
   ↓
Reference
   ↓
Chunk
   ↓
Embedding
   ↓
Retrieval
   ↓
AI Context
   ↓
Explanation
   ↓
Question Generation
   ↓
Validation
   ↓
Publishing
   ↓
Student
```

## Ownership

- `Curriculum`, `Topic`, `Learning Objective`, and `Reference` are owned by the Academic Catalogue.
- `Chunk` and `Embedding` are owned by the Academic Content / AI Service boundary.
- `Retrieval`, `AI Context`, and `Explanation` are owned by the AI Service.
- `Question Generation`, `Validation`, and `Publishing` bridge the AI Service and CBT / student experience.

## Principles

- AI outputs must not redefine curriculum truth.
- The AI service must use the catalogue as the source of syllabus structure.
- Embeddings are artifact versions that may be regenerated when models or chunking change.
- Validation is required before publishing AI-generated assessment or explanations.
- Student-facing experiences should label AI-generated content with provenance and support uncertainty handling.

## Important notes

- `Chunk` and `Embedding` artifacts are derived, not authoritative.
- `Retrieval` should return catalogue-aware results, not raw content alone.
- `AI Context` should include versioned curriculum and topic metadata when available.
- `Question Generation` should source its prompts and templates from published domain models.
- `Publishing` should be gated by validation and aligned with the platform’s audit model.
