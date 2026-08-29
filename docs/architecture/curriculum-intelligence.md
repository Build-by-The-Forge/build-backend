# Curriculum Intelligence Architecture Specification

## 1. Overview & System Purpose

Curriculum Intelligence is the foundational domain for the BUILD learning platform. It captures, versions, validates, and exposes authoritative academic benchmarks (such as NUC CCMAS) and governs how universities (tenants) adopt and enrich those standards to produce personalized, accredited student learning pathways.

---

## 2. The 3-Tier Academic Curriculum Hierarchy

BUILD organizes academic knowledge into three distinct, non-competing layers:

```text
                               3-TIER ACADEMIC HIERARCHY

1. NATIONAL BENCHMARK BASELINE (NUC CCMAS)
   "What NUC regulatory authority says"
   ├── BenchmarkCurriculum (Discipline, Programme, Version, Provenance)
   ├── BenchmarkCourse (Code, Title, Minimum Credit Units, Level, Semester)
   ├── BenchmarkTopic (Sequence, Title, Scope)
   └── BenchmarkOutcome (Sequence, Description, Bloom Taxonomy Level)
                    │
                    │ Adopted by Institution (e.g. FUTA, UNILAG)
                    ▼
2. INSTITUTIONAL CURRICULUM POLICY (Adoption & Overrides)
   "What the University has decided to deliver"
   ├── InstitutionalCurriculumAdoption (Programme, Academic Session)
   └── CurriculumOverride (Audited record: field, original, override, reason, created_by)
                    │
                    │ Resolved dynamically
                    ▼
3. EFFECTIVE CURRICULUM (Read Mode & Study Path)
   "What the student and lecturer actually see and operate under"
   └── Effective Course / Topic / Outcome Tree
       $$\text{Effective Value} = \text{Institutional Override if present else Baseline}$$
```

### Invariants:
1. **National Baseline is Immutable:** Institutional changes (such as FUTA changing `COS102` from 2 units to 3 units) do **not** mutate the global benchmark standard.
2. **Overrides are Audited:** Every institutional modification is recorded as an auditable `CurriculumOverride` entity with author identity, timestamp, justification, and approval status.
3. **Reproducibility:** Student learning history, exam attempts, and Read Mode records remain permanently bound to the effective curriculum active at the time of study.

---

## 3. Identity, Roles & Access Scopes

BUILD enforces a clear separation between **Identity**, **Role (Capabilities)**, and **Scope (Boundaries)**:

```text
USER IDENTITY (Person)
  ├── id, email, full_name, auth_credentials
  │
  └── ASSIGNMENTS
       ├── Role: "Student"             │ Scope: University="FUTA", Department="Computer Science"
       ├── Role: "Lecturer"            │ Scope: University="FUTA", Department="Computer Science"
       └── Role: "University Admin"    │ Scope: University="FUTA" (Tenant-wide)
```

| Dimension | Question Answered | Examples |
| :--- | :--- | :--- |
| **User Identity** | *Who are you?* | `olamide@example.com` |
| **Role** | *What capabilities do you possess?* | `student`, `lecturer`, `hod`, `faculty_admin`, `admin`, `owner` |
| **Scope** | *Where can you exercise those capabilities?* | Platform-global, Tenant (`FUTA`), Department (`Computer Science`), Course (`COS102`) |

---

## 4. Ingestion, Extraction & Governance Pipeline

```text
1. CAPTURE (Phase 4A.1)
   Scheduler / Trigger
   → Fetches latest source metadata & raw document
   → Computes SHA-256 Checksum
   → If hash unchanged: No-op / Idempotent return
   → If hash changed: Save immutable `CurriculumSnapshot` + upload raw artifact

2. EXTRACT (AI Service / Parser Worker)
   → AI Service parses unstructured document
   → Delivers structured JSON candidate payload with versioned parser metadata
   → Saves `BenchmarkCurriculum` (Status: `CANDIDATE`)

3. VALIDATE (Backend Invariant Engine - Phase 4A.3)
   → Deterministic validation (code uniqueness, credit bounds, sequence sanity)
   → Status transitions: `CANDIDATE` → `VALIDATED` or `REJECTED`

4. DIFF (Deterministic Engine - Phase 4A.5)
   → Compares candidate against active version
   → Generates structured diff (added/removed courses, credit shifts, topic changes)

5. ACTIVATE (Promotion & Version Governance - Phase 4A.4)
   → Prior `ACTIVE` version transitions to `SUPERSEDED`
   → `VALIDATED` candidate transitions to `ACTIVE`
   → Emits `curriculum.version_activated` domain event
```

---

## 5. Natural-Language Assisted Curriculum Governance

For institutional adjustments, administrators can formulate requests naturally while the backend remains the deterministic enforcement authority:

```text
Administrator: "Change COS 102 to 3 credit units"
                     │
                     ▼
AI Interpretation: { "entity": "BenchmarkCourse", "code": "COS102", "field": "credit_units", "new_value": 3 }
                     │
                     ▼
Backend Validation: Checks FUTA adoption & academic session validity
                     │
                     ▼
Admin Preview: Displays before/after diff for human confirmation
                     │
                     ▼
Approval: Records `CurriculumOverride` → Dynamic Effective Curriculum reflects 3 units
```

---

## 6. Phased Implementation Roadmap

```text
4A.1 — Source & Snapshot Management (Global registry, SHA-256 drift check)      ✅ COMPLETE
4A.2 — Benchmark Curriculum Tree (National baseline hierarchy & ingestion)       ✅ COMPLETE
4A.3 — Candidate & Structural Validation Engine (Credit, code & sequence checks)  ⬅️ NEXT
4A.4 — Version Activation & Exclusive Active Invariant (ACTIVE -> SUPERSEDED)
4A.5 — Deterministic Diff Engine (Course/Topic/Credit change detection)
4A.6 — Administrative Benchmark Governance & Audit APIs
4A.7 — Institutional Curriculum Adoption & Overrides (FUTA -> CCMAS baseline)
4A.8 — Dynamic Effective Curriculum Resolution Engine (Read Mode skeleton)
```
