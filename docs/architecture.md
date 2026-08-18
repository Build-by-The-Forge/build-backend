# BUILD Documentation Handbook

This handbook organizes BUILD documentation into a stable architecture reference.
It is the starting point for contributors who need to understand the platform design, contracts, decisions, events, and vision.

## Read in order

1. `docs/architecture/overview.md`
   - High-level architecture introduction and source-of-truth guidance.
2. `docs/architecture/academic-knowledge-model.md`
   - Canonical academic catalogue model for v0.4.0.
3. `docs/architecture/system-data-flow.md`
   - End-to-end platform flow from curriculum through AI and CBT.
4. `docs/architecture/public-id-strategy.md`
   - External identifier policy for stable public IDs.
5. `docs/architecture/versioning.md`
   - Versioning rules for curriculum, content, AI, and embeddings.
6. `docs/domain-map.md`
   - Frozen domain model and entity graph for implementation.

## Architecture docs

- `docs/architecture/overview.md` — architecture handbook introduction.
- `docs/architecture/academic-knowledge-model.md` — academic knowledge model and bounded context map.
- `docs/architecture/system-data-flow.md` — how data flows through BUILD.
- `docs/architecture/public-id-strategy.md` — public ID policy and naming conventions.
- `docs/architecture/versioning.md` — versioning strategy for curriculum and AI artifacts.
- `docs/architecture/academic-catalogue-specification.md` — catalogue-specific architecture details.

## Contracts

Contracts describe the shared boundaries between bounded contexts.

- `docs/contracts/README.md`
- `docs/contracts/catalogue-contract.md`
- `docs/contracts/content-contract.md`
- `docs/contracts/ai-contract.md`
- `docs/contracts/identity-contract.md`
- `docs/contracts/events-contract.md`

## Events

Event catalogs describe emitted events, payload shapes, and consumer expectations.

- `docs/events/catalogue-events.md`

## Vision

Vision documents define strategy, source-of-truth policy, reference data, and AI lifecycle.

- `docs/vision/academic-data-strategy.md`
- `docs/vision/reference-data-strategy.md`
- `docs/vision/ai-knowledge-lifecycle.md`

## Decisions and ADRs

- `docs/decisions/001-source-of-truth.md`
- `docs/adr/` — add future architectural decision records here.

## Domain reference

- `docs/domain-map.md`

## Project templates

- `docs/module-template.md`

## Notes

- `docs/alembic.md` and `docs/phase-2-iam-roadmap.md` are project-specific references and remain at the root.
