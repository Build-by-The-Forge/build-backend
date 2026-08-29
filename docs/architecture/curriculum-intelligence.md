# Curriculum Intelligence Architecture Specification

## 1. Overview & System Purpose

Curriculum Intelligence is the foundational domain for the BUILD learning platform. It captures, versions, validates, and exposes authoritative academic benchmarks (such as NUC CCMAS) and governs how universities (tenants) adopt and enrich those standards.

---

## 2. Core Entities & Aggregate Boundaries

```text
                               GLOBAL BENCHMARK DOMAIN

┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CurriculumSource (Aggregate Root)                                                      │
│ - id: CurriculumSourceId                                                               │
│ - code: str ("CCMAS_NUC")                                                              │
│ - name: str ("NUC Core Curriculum and Minimum Academic Standards")                     │
│ - base_url: str                                                                        │
│ - sync_interval_days: int (default 30)                                                 │
│ - status: SourceStatus (ACTIVE, PAUSED)                                                │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ 1:N
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CurriculumSnapshot (Entity / Audit Provenance)                                         │
│ - id: CurriculumSnapshotId                                                             │
│ - source_id: CurriculumSourceId                                                        │
│ - fetched_at: datetime                                                                 │
│ - content_sha256: str                                                                  │
│ - raw_artifact_uri: str (S3/GCS object path)                                           │
│ - status: SnapshotStatus (CAPTURED, EXTRACTING, EXTRACTED, FAILED)                     │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ 1:1
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CandidateCurriculum (Draft Entity)                                                     │
│ - id: CandidateId                                                                      │
│ - snapshot_id: CurriculumSnapshotId                                                    │
│ - programme_code: str ("CSC")                                                          │
│ - candidate_version: str ("2026.01")                                                   │
│ - payload_json: dict (unvalidated extracted tree)                                      │
│ - status: CandidateStatus (PENDING_VALIDATION, VALIDATED, REJECTED)                    │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Promoted via Validation
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ BenchmarkCurriculum (Aggregate Root)                                                   │
│ - id: BenchmarkCurriculumId                                                            │
│ - candidate_id: CandidateId                                                            │
│ - programme_code: str ("CSC")                                                          │
│ - discipline_name: str ("Computer Science")                                            │
│ - version: str ("2026.01")                                                             │
│ - status: BenchmarkStatus (VALIDATED, ACTIVE, SUPERSEDED, ARCHIVED)                    │
│ - effective_date: date                                                                 │
│ ├── BenchmarkCourse (code, title, credit_units, level, semester, is_compulsory)         │
│ │    ├── BenchmarkTopic (title, sequence, description)                                 │
│ │    └── BenchmarkOutcome (description, sequence, bloom_level)                         │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Diff against prior ACTIVE
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CurriculumDiff (Value Object / Historical Audit)                                       │
│ - from_version_id: BenchmarkCurriculumId                                               │
│ - to_version_id: BenchmarkCurriculumId                                                 │
│ - added_courses: list[str]                                                             │
│ - removed_courses: list[str]                                                           │
│ - modified_courses: list[dict] (e.g. credit changes, topic additions)                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Institutional Adoption Model (Tenant Catalogue)

When a tenant (e.g. Federal University of Technology Akure) sets up a course in its department catalogue, it references the national benchmark:

```text
BenchmarkCourse (CSC 201 — Computer Programming I, 3 Credits)
       │
       │ adopted_by (tenant_id = "tenant-futa")
       ▼
Tenant Course (CSC 201 — Computer Programming I, 3 Credits, Dept of Computer Science)
       │
       ├── BenchmarkTopic Adoption (Arrays, Pointers, Structs)
       └── Local Topic Enrichment (e.g., FUTA Lab Exercise Module)
```

### Invariants:
1. A tenant course adopting a benchmark course inherits the benchmark code, title, and minimum credit requirements by default.
2. Local departmental enrichments (extra topics, specialized reference materials) are added as tenant-scoped children without mutating the global benchmark.

---

## 4. Ingestion, Validation & Activation Pipeline

```text
1. CAPTURE
   Scheduler triggers `curriculum.sync_check`
   → Fetches latest source metadata & raw document
   → Computes SHA-256
   → If hash unchanged: Log "No drift" & terminate
   → If hash changed: Save `CurriculumSnapshot` + upload raw artifact to object storage

2. EXTRACT (AI Service / Parser Worker)
   → AI Service parses raw artifact
   → Produces structured JSON tree
   → Saves `CandidateCurriculum` (Status: `PENDING_VALIDATION`)

3. VALIDATE (Backend Invariant Engine)
   → Course code uniqueness within programme
   → Valid credit units (1..6 per course)
   → Every course has >= 1 topic
   → Monotonically increasing sequences
   → If valid: Status `VALIDATED`
   → If invalid: Status `REJECTED` with validation error log

4. DIFF (Deterministic Engine)
   → Loads current `ACTIVE` BenchmarkCurriculum for programme code
   → Computes deterministic diff (added/removed/modified courses & topics)
   → Attaches `CurriculumDiff` to candidate

5. ACTIVATE (Administrative Governance / Promotion)
   → Current `ACTIVE` version transitions to `SUPERSEDED`
   → `VALIDATED` candidate transitions to `ACTIVE`
   → Emits `curriculum.version_activated` domain event
```

---

## 5. Phased Implementation Breakdown (4A Slices)

To maintain safety, zero-downtime migrations, and high test coverage, Phase 4A will be executed in the following vertical slices:

### **Slice 4A.1: Source & Snapshot Management**
* Domain entities: `CurriculumSource`, `CurriculumSnapshot`.
* Repositories & SQL models: `curriculum_sources`, `curriculum_snapshots`.
* Ingestion capture handler & SHA-256 drift detection.
* Integration tests for source registry and snapshot deduplication.

### **Slice 4A.2: Benchmark Curriculum Tree**
* Domain entities: `BenchmarkCurriculum`, `BenchmarkCourse`, `BenchmarkTopic`, `BenchmarkOutcome`.
* Repositories & SQL models: `benchmark_curricula`, `benchmark_courses`, `benchmark_topics`, `benchmark_learning_outcomes`.
* Persistence mappers and repository queries.

### **Slice 4A.3: Candidate & Validation Engine**
* Domain entity: `CandidateCurriculum`.
* Invariant validator checking credit bounds, code uniqueness, sequence ordering, and topic presence.
* Candidate rejection and validation lifecycle tests.

### **Slice 4A.4: Version Activation & Exclusive Active Invariant**
* `ActivateBenchmarkVersionHandler` state machine (`VALIDATED` $\to$ `ACTIVE`, prior `ACTIVE` $\to$ `SUPERSEDED`).
* Atomic transaction with database unique constraint ensuring only 1 `ACTIVE` version per programme code.

### **Slice 4A.5: Deterministic Diff Engine**
* `CurriculumDiffService` comparing course codes, credit changes, topic additions/deletions, and outcome modifications.
* Structured diff serialization.

### **Slice 4A.6: Administrative Benchmark APIs & Authorization**
* Internal/Admin endpoints:
  * `POST /curriculum/sources`
  * `GET /curriculum/sources`
  * `GET /curriculum/benchmarks`
  * `GET /curriculum/benchmarks/{id}`
  * `GET /curriculum/benchmarks/{id}/diff`
  * `POST /curriculum/benchmarks/{id}/activate`
* RBAC enforcement (`admin`, `owner` only).

### **Slice 4A.7: Tenant Adoption Linking (Catalogue Bridge)**
* Add optional `benchmark_course_id` to `CourseModel` and `benchmark_topic_id` to `TopicModel`.
* Migration to link existing catalogue courses to national benchmark standards.

---

## 6. Definition of Done for Phase 4A

* ✅ All 7 slices implemented and tested.
* ✅ Full regression test suite passing (`pytest`).
* ✅ Strict static typing clean (`mypy app`).
* ✅ Linter clean (`ruff check app tests`).
* ✅ Historical reproducibility and exclusive active invariants mathematically and practically verified.
