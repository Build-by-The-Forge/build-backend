# ADR 001: Source of Truth for Academic Curriculum

## Status

Accepted

## Context

BUILD is evolving from a platform foundation to an Academic Knowledge Platform.
The system must make a clear architectural distinction between the canonical curriculum definition and the material or media used to teach it.

Without a source-of-truth decision, future teams may incorrectly allow uploaded content or AI outputs to redefine the academic syllabus.

## Decision

The Academic Catalogue bounded context is the only owner of official curriculum definitions.
Only the following sources may define curriculum in BUILD:

- `NUC CCMAS`
- `FUTA Senate` approved curricula
- Faculty curriculum committee approvals
- Department programme handbooks that are explicitly published and governed
- Official catalogue definitions authored by BUILD administrators in the `Academic Catalogue`

The following are explicitly not allowed to redefine curriculum truth:

- user-uploaded files, PDFs, slides, or notes
- AI-generated summaries, explanations, or inferred curriculum
- student-generated content
- unofficial or unapproved departmental documents

Uploaded files and content assets are permitted as supplementary learning resources, not as canonical curriculum definitions.

## Consequences

- Curriculum remains stable and auditable.
- The platform can safely build AI, content, and assessment services on top of a single canonical academic model.
- Future catalogue consumers will not have to reconcile conflicting source authorities.
- Governance is simplified because only designated academic roles may change curriculum definitions.
- The contract between `Catalogue` and `Content` remains clear: catalogue owns academic truth, content owns learning resources.

## Non-goals

- This decision does not prevent BUILD from ingesting unstructured documents for content extraction.
- It does not prevent AI from generating study aids.
- It does not prevent the platform from indexing or annotating uploaded content, as long as the catalogue remains the source of truth.
