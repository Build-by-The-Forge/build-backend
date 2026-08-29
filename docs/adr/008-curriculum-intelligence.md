# ADR 008: Curriculum Intelligence Architecture

## Status

Accepted

## Date

2026-08-29

## Context

BUILD is a personalized learning ecosystem where student study paths (Read Mode, CBT practice, AI tutoring) are grounded in authoritative academic standards.

In the Nigerian university system, the National Universities Commission (NUC) publishes Core Curriculum and Minimum Academic Standards (CCMAS), which are periodically updated. Individual universities (tenants) adopt and enrich these benchmark standards with institutional courses, department requirements, and local teaching variations.

Previously, BUILD's catalogue bounded context represented academic data purely inside tenant boundaries (`tenants -> faculties -> departments -> programmes -> courses`). It lacked:
1. A global, national benchmark curriculum layer independent of any single university tenant.
2. Provenance tracking for external curriculum sources (source URLs, snapshots, checksums).
3. A candidate extraction, deterministic validation, and version activation pipeline.
4. Deterministic change detection (diffing) to track educational drift over time.
5. Protection against historical study state mutations when national benchmarks change.

## Decision

BUILD will implement **Curriculum Intelligence** as a dedicated subsystem bridging external regulatory standards with institutional catalogues:

```text
                 EXTERNAL AUTHORITY (NUC CCMAS)
                               │
                               ▼
                        CurriculumSource
                               │ (monthly sync check / checksum)
                               ▼
                       CurriculumSnapshot (SHA-256 + Object Storage URI)
                               │
                        (AI extraction)
                               │
                               ▼
                      CandidateCurriculum
                               │
                 (Deterministic Backend Validation)
                               │
                               ▼
                      BenchmarkCurriculum
                 (Exclusive ACTIVE per discipline)
                               │
                               ▼
                  Tenant-Specific Catalogue
                 (Adoption & Local Enrichment)
                               │
                               ▼
                   Read Mode / Study Path
```

### 1. Global Benchmark vs. Institutional Catalogue Separation
- **Global Benchmark Layer:** `CurriculumSource`, `CurriculumSnapshot`, `BenchmarkCurriculum`, `BenchmarkCourse`, `BenchmarkTopic`, `BenchmarkOutcome`. These represent national standards (CCMAS) and are tenant-agnostic.
- **Institutional Catalogue Layer:** `Tenant`, `Faculty`, `Department`, `Programme`, `CurriculumVersion`, `Course`, `Topic`, `LearningOutcome`. These represent university-specific implementations and point to benchmark entities via explicit foreign keys (`benchmark_course_id`, `benchmark_topic_id`).

### 2. Role of Existing `CurriculumVersion`
The existing `CurriculumVersion` aggregate represents an **institutional delivery package** (e.g. FUTA Computer Science 2026/2027 curriculum version). It is preserved for university-level cohort delivery and is not conflated with the national `BenchmarkCurriculum`.

### 3. Ingestion Pipeline: Source → Snapshot → Candidate → Active
- **CurriculumSource:** Registry of external authority endpoints, parser configurations, and sync frequencies.
- **CurriculumSnapshot:** Immutable record of fetched raw documents, storing metadata, SHA-256 checksums, and storage URIs (raw files reside in object storage, not PostgreSQL byte arrays).
- **CandidateCurriculum:** Unverified draft produced by extraction workers. It can be rejected without affecting the existing active standard.
- **BenchmarkCurriculum:** Formally validated and activated version. Only **one** version may be `ACTIVE` per discipline benchmark at any given time; prior active versions transition to `SUPERSEDED` and become permanently immutable.

### 4. Deterministic Validation & Change Detection
- The Backend enforces strict structural invariants before candidate activation (unique course codes, non-empty topic lists, credit thresholds).
- Diffing between versions ($V_1 \to V_2$) is computed deterministically by the backend (added/removed courses, modified topics, credit shifts) rather than inferred by AI.

### 5. Backend vs. AI Service Responsibility
- **Backend owns:** Ingestion jobs, source provenance, SHA-256 verification, validation invariants, version activation state machines, deterministic diffs, and authorization.
- **AI Service owns:** Unstructured PDF/web parsing, OCR, semantic cleanup, and entity normalization into candidate schemas. AI does not authoritatively activate curriculum standards.

### 6. Historical Reproducibility
When a student studies a topic or completes an assessment, the historical record references the exact `benchmark_version_id` active at that time. Subsequent curriculum activations never mutate past student learning records.

## Consequences

### Positive
- **Authoritative Grounding:** Read Mode and AI Tutoring always cite verified national and institutional curriculum standards.
- **Zero Historical Drift:** Student progress records remain completely reproducible across multi-year academic changes.
- **Fault-Tolerant Ingestion:** Erroneous external scrapes or candidate extractions are stopped at the candidate validation gate before reaching students.
- **Tenant Flexibility:** Universities can enrich standard benchmark topics without breaking national accreditation compliance.

### Trade-offs & Mitigations
- **Storage & Relational Complexity:** Requires maintaining both global benchmark and tenant catalogue hierarchies.
  * *Mitigation:* Clear naming conventions (`Benchmark*` vs. `Course/Topic`) and explicit foreign key adoption links.
- **Asynchronous Sync Overhead:** Ingestion, extraction, and validation require asynchronous background task orchestration.
  * *Mitigation:* Implement standard job submission (`202 Accepted`) and transactional outbox patterns.
