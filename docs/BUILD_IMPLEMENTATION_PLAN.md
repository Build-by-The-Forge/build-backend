# BUILD Implementation Plan

**Status:** approved by the user on 2026-11-20 (relayed by the review session). Governance rules in section 12 bind every lane.

**What this is:** the delivery plan from today to release. It states what is built, in what order, by whom, and what counts as done.

**What this is not:**
- It is not a tracker. `docs/milestone-register.md` stays the single tracker; section 11 of this plan only maps phases to its milestones.
- It is not a status report. Where the repositories stand today is in `docs/BUILD_IMPLEMENTATION_BASELINE.md`.
- It does not amend the PRD. Where this plan and `docs/BUILD_MASTER_PRD.md` disagree, the baseline lists the conflict, and the PRD amendment is its own PR needing reviewer approval.

## 1. Executive summary and philosophy

BUILD is a learning platform for FUTA (Nigeria) students. A student registers, sets their academic context, uploads or reads course material, asks a tutor questions grounded in that material, practises, sits CBTs, and sees results and progress.

**BUILD owns the educational foundation; models assist.** The backend decides who may see what, what a score is, and what an answer is allowed to claim. The AI service owns retrieval, evidence and grounding. A model, hosted or on the device, generates text from evidence BUILD hands it. It never decides permissions, scores, entitlements or grounding, and swapping a model never changes those guarantees.

Two releases:

| Release | What a student gets | Where it must work |
|---|---|---|
| **R1** | The core journey, with a grounded tutor, CBT and results, and downloaded course material | Staging, one student end to end, then production |
| **R2** | Offline AI inference, flashcards, knowledge trees, study plans, personalisation | After R1; the offline benchmark continues during R1 so R2 starts from evidence |

## 2. Scope

### 2.1 Release 1

- Registration, login, sessions, academic onboarding and the academic profile (S-01, S-02).
- Dashboard summary (S-03).
- Study Shelf, upload, ingestion, quarantine and scanning, Read Mode (S-04, S-05, S-07).
- The AI Tutor with conversations, citations, provenance, abstention (S-06).
- Practice kept apart from official CBT (S-10) and CBT with authoritative results (S-11, S-12).
- Progress (S-13) and settings (S-14).
- Entitlements as backend-owned infrastructure; no payment experience.
- Offline continuity limited to **practice only** (section 2.3): downloaded course packs, offline retrieval over them, offline practice with provisional scores.
- GCP staging and the end-to-end acceptance suite.

### 2.2 Release 2

- Offline AI inference (a small on-device model portfolio, chosen by benchmark).
- Flashcards, knowledge trees (S-08), study plans (S-09), the bounded agentic study planner.
- Personalisation, including Learning Memory, only after its production gate (`GATE_OPEN`) is approved. Nothing in this plan opens it.

### 2.3 Offline decision for R1 (approved 2026-11-20)

- **Practice-only offline in v1.** Official CBT attempts, submission, grading and results are online-only.
- Offline practice scores are provisional until the server validates them on reconnect.
- The offline authorisation lease (72 hours, monotonic time, failing closed) and its sync design stay as approved in `docs/m3-d-design.md`.

### 2.4 Deferred (not in R1 or R2 unless a later decision says so)

Lecturer and contributor workflows, administrative and owner dashboards, social groups and leaderboards, payment experiences, advanced campus GIS, institutional analytics, lecturer video and CMS (PRD §0.5). Personas other than students log in nowhere in this delivery.

## 3. Requirements

| Requirement | Value |
|---|---|
| Platform | Android 14 and later |
| Minimum device | 4 GB RAM |
| App download | Under 100 MB. Model weights and content packs are separate, optional downloads, never bundled |
| Language | English only |
| Authority | The backend alone for identity, tenancy, authorisation, entitlements, scores and release of results |
| Providers | No production provider receives student or institutional passages until G-33 is approved for it |
| Spending | No infrastructure spending and no paid provider calls without the user's explicit authorisation |

These numbers are requirements to test against, not measurements. Phase 8 measures them.

## 4. Repository ownership

| Repository | Owns | Does not own |
|---|---|---|
| `build-backend` | Public API, identity, tenancy, authorisation, academic truth, catalogue, content rights, assessments and results, entitlements, the mobile contract (`contracts/mobile/`), the PRD, this plan, the milestone register | Retrieval, model calls, embeddings |
| `ai-service` | Model Gateway and providers, ingestion and OCR, retrieval and evidence, grounding checks, generation, agents and tools, evaluation sets | Public routes, identity, permissions, scores |
| `Build-UI` | The React Native Android client, secure token storage, local storage, the on-device runtime in R2 | Any permission, score or entitlement decision; never calls the AI service |

Backend and AI service talk only through signed requests and signed responses (Service Signature v1). Mobile talks to the backend only.

## 5. Architecture

Six layers, from the student outward to the model:

| Layer | Responsibility | Lives in |
|---|---|---|
| 1. Client | Screens, local state, offline store | `Build-UI` |
| 2. Public API | One contract, one error shape, authentication, entitlements, rate limits | `build-backend` |
| 3. Academic authority | Tenancy, membership, content rights, the one read policy, assessments, results | `build-backend` |
| 4. AI boundary | Signed dispatch, `denied_assets`, scope assignments, provenance check on every answer | both |
| 5. Grounded intelligence | Retrieval, evidence validation, routing, citations, abstention, tools | `ai-service` |
| 6. Model execution | The Model Gateway: provider eligibility, fallback, deadlines, budgets, structured output, usage accounting | `ai-service` |

### Online request flow

1. The client calls the backend with the student's token.
2. The backend authenticates, checks the entitlement and the budget, and builds the AI request: the actor, the question, the scope, `denied_assets` (at most 1,000 entries).
3. The backend signs and sends it. The AI service verifies the signature, the nonce and the request body.
4. The AI service retrieves within the allowed scope, validates evidence, routes (naive or bounded agentic RAG), calls the model through the gateway, and checks grounding. With too little evidence it abstains.
5. It returns a signed response with `sources_used`.
6. The backend verifies the signature and the exact request, then checks `sources_used` and every citation against the student's current read permissions. Any failure withholds the whole answer (`ANSWER_WITHHELD`), cited or not.
7. The backend stores and returns the answer.

## 6. Phases

Phases overlap. Each states its exit evidence. Section 11 maps them to the register.

### Phase 0: audit
Record where every repository stands, label every claim, and list documentation conflicts. **Output:** `docs/BUILD_IMPLEMENTATION_BASELINE.md`. Phase 0 runs alongside the active lanes. It gates nothing.

### Phase 1: architecture and contracts
- The student journey contracts (design merged in #112), then the contract PRs per milestone.
- The shared learning contracts and tool definitions that online, offline and learning capabilities reuse.
- The offline content-pack contract and the bounded study-planner design.
- **Exit:** contracts merged with the drift gate green; each design approved before its implementation.

### Phase 2: backend foundation
| Part | Content |
|---|---|
| M3-D | Student uploads and content rights: PRs 7 to 15 of `docs/m3-d-design.md` |
| M3-E | Assessment contract: complete pending the reviewer's check |
| M3-F | Conversations, cited chat |
| M4 | Retrieval eligibility and citation authorisation |
| M5 | Typed client, auth and session, error handling |
| M6 | Student workflows and screens |
| M7 | The pinned, release-blocking integration gate |
| Entitlements | Free, Plus, Pro, Campus; the backend is the only authority |
| Offline authorisation and sync | The lease, pack download and revocation, provisional-score validation |

**Exit:** the M3 exit checklist in the register, then M4 to M7 acceptance.

### Phase 3: AI foundation
- The Model Gateway as the one model execution boundary (AI-01; consolidation done).
- **Gemini** through the gateway adapter (ai-service #65), passages disabled until G-33 is approved.
- **Fireworks**, governance first: reconcile the PRD and documentation, record G-33 for both providers, verify terms and model IDs, reviewer approval, then an adapter after #65. Fireworks is not adopted by this plan.
- Routing between providers and between naive and agentic RAG; per-request and per-tenant budgets.
- **Evaluation of 100 tasks:** 50 RAG, 30 orchestration, 20 question generation. A baseline is recorded before any threshold.
- **Exit:** gateway evidence, an approved G-33 for each provider used, the 100-task baseline.

### Phase 4: grounded intelligence
Ingestion and OCR hardening; retrieval quality on real material (62.5% recall@5 on real first-semester FUTA material, against 94.6% on the controlled set); naive RAG, then bounded agentic RAG; citations mapped from chunk metadata; real-material evaluation. **Exit:** a measured improvement on real material, with each variable changed alone.

### Phase 5: offline AI
Benchmark the on-device portfolio on real devices; build the offline retrieval and the content-pack runtime; local inference in R2. **Offline model roles are assigned only after benchmarking.** Targets: Qwen3.5-0.8B, Qwen3-1.7B, SmolLM2-1.7B. Comparisons: Qwen3.5 2B and 4B, Gemma 4 E2B, Gemma 3n E2B, Ministral 3 3B, Phi-4-mini. The benchmark continues during R1.

### Phase 6: Android app
Typed client from the contract; secure storage; single-flight refresh; onboarding, dashboard, shelf, upload, tutor, practice, CBT, results; removal of fixtures and fabricated results (the CBT screen's hardcoded 95%).

### Phase 7: offline continuity
Pack download, integrity check, lease, revocation, practice, provisional scores, reconnect validation, sync. In R1 this is practice-only (section 2.3).

### Phase 8: testing and benchmarking
- Unit, PostgreSQL, boundary, contract drift, end to end, device.
- **Emulator limits:** an emulator proves behaviour, not performance. Memory, thermal, battery and latency claims come only from real target devices, and a result states which device ran it.
- Offline benchmark on real devices; the 4 GB RAM and 100 MB download requirements measured.

### Phase 9: security and governance
G-33 per provider, retention and deletion of derived data (G-32), provider-call audit, the memory gate staying closed, dependency and image scanning, the open incident in the register.

### Phase 10: deployment
GCP staging (Cloud Run, Cloud SQL with PostgreSQL 17 and pgvector, managed Redis, Cloud Storage), monitoring, backups and a restore drill, update delivery. **Nothing is created or paid for without explicit authorisation.**

### Phase 11: end-to-end release
One student completes the journey on staging, then the release acceptance checklist (section 10) on pinned SHAs.

## 7. Workstreams

| Stream | Scope | Phases |
|---|---|---|
| **A. Backend and contracts** | M-track, entitlements, offline authorisation | 1, 2, 7 |
| **B. AI intelligence** | Gateway, providers, routing, retrieval, evaluation, agents | 3, 4, 5 |
| **C. Mobile** | Android client, offline store | 6, 7 |
| **D. Platform and governance** | Deployment, security, G-33, testing, benchmarks, documentation | 0, 8, 9, 10, 11 |

Concurrency: three to four lanes at once on the 8 GB development laptop. Heavy jobs (OCR runs, image builds, model benchmarks) run one at a time.

## 8. Dependencies

| Work | Needs first |
|---|---|
| Student upload routes opened | M3-D PRs 1, 4 and 6 deployed (merged); PR 7 onward |
| Tutor conversations | M3-D provenance; the M3-F contract (#90) |
| M4 | M3-D and M3-F |
| Mobile screens | M5, plus the contract for each screen |
| Gemini on student passages | G-33 approved and a paid-tier key |
| Fireworks adapter | The governance steps in Phase 3, then #65 merged |
| Agentic RAG | The tool registry design, retrieval evidence on real material |
| Offline inference | Benchmark results on real devices |
| Offline practice | The authorisation lease and pack contract |
| Learning Memory | L4 and the production gate |
| Staging | Explicit spending authorisation |
| Release acceptance | M7 on pinned SHAs |

## 9. Engineering standards and completion states

- **One concern per commit; one concern per PR.** Stage explicit paths.
- Every claim about code in a document is checked against the repository and cites a path.
- A closed gap in `contracts/mobile/gaps.yaml` needs its proof test.
- Merge only on an explicit "APPROVED — merge eligible" for the exact head SHA.

**Completion states.** Only these labels are used, and "done" is not one of them:

| State | Meaning |
|---|---|
| Implemented on main | Merged, reachable and tested |
| Merged, verification pending | Merged; acceptance evidence not yet recorded |
| Open PR | Under review; not on main |
| Design only | An approved or proposed design; no code |
| Not started | Nothing exists |
| Blocked | Waiting on a named dependency |
| Deferred | Out of scope by decision |

A milestone is complete only when its acceptance criteria hold and the evidence exists.

## 10. Risks and release acceptance

### Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Retrieval quality on real material is 62.5% recall@5 | Weak tutor answers | Phase 4 one variable at a time; abstention |
| 1,459 scanned pages still need OCR | Missing content | The OCR lane; cached, sharded runs |
| Provider terms unverified (G-33) | Cannot send passages | Drafts, then the user and reviewer decide |
| Provider and model identifiers unverified | Wrong build | Verify at startup against the provider |
| 8 GB laptop | Slow or failed heavy jobs | Three to four lanes; heavy jobs serial |
| Emulator results taken as device results | False claims | State the device in every result |
| 4 GB RAM and 100 MB targets unmeasured | Release blocker found late | Measure in Phase 8, early on a prototype |
| Scope growth from R2 into R1 | R1 slips | The two-release split; changes need a decision |
| Mobile built against drifting contracts | Rework | Drift gate; fixtures before screens |
| Alembic head contention | Migration conflicts | Ask the head's owner for the next revision |
| Open incident (`067d980` purge) | Exposed audit file | Register, until GitHub confirms |

### Release acceptance checklist

- [ ] One student completes the journey on staging: register, onboard, upload, ingest, ask a grounded question, practise, sit a CBT, see results.
- [ ] A revoked source withholds the whole answer.
- [ ] EICAR is rejected; a quarantined document is never served.
- [ ] No fabricated result or fixture reaches a production build.
- [ ] M3 exit checklist and M4 to M7 acceptance recorded with exact SHAs.
- [ ] G-33 approved for every provider that receives student passages.
- [ ] `GATE_OPEN` is `False` and verified in the built image.
- [ ] The 100-task evaluation baseline recorded; real-material retrieval measured.
- [ ] Device results for the 4 GB RAM and 100 MB requirements, with the device named.
- [ ] Offline practice works under the lease, and official CBT is refused offline.
- [ ] Backups restored in a drill; monitoring and alerts live.
- [ ] Every gate's own checks green on the pinned SHAs, with run links.

## 11. Phase-to-milestone mapping

The mapping is held in `docs/milestone-register.md`, section "Phase to milestone mapping". There is one tracker.

## 12. Governance rules

1. **No implementation by assumption.** Each feature has an approved design or contract first, and a lane states its assumptions in its PR.
2. Gemini and Fireworks are not approved for student material until G-33 is approved for each and a paid-tier key exists. `GATE_OPEN` stays `False`.
3. The milestone register is the single tracker.
4. No infrastructure spending and no paid provider calls without explicit authorisation.
5. No false completion claims. A state not in section 9 is not used.
6. Phase 0 and the baseline run alongside active lanes and gate nothing.
7. A design approval is not permission to expose a route.

## 13. Initial backlog

| ID | Item | Phase | State |
|---|---|---|---|
| B-001 | Baseline: build-backend, ai-service and Build-UI default-branch SHAs and open PRs | 0 | In `BUILD_IMPLEMENTATION_BASELINE.md` |
| B-002 | Baseline: implemented, merged-pending, open, design-only, not-started per area | 0 | In the baseline |
| B-003 | Baseline: documentation conflicts | 0 | In the baseline |
| B-004 | Baseline: gap snapshot from `gaps.yaml` | 0 | In the baseline |
| B-005 | Baseline: running lanes and owners | 0 | In the baseline |
| B-006 | PRD amendment: practice-only offline, R1/R2, provider section under reconciliation | 1 | Draft PR, needs reviewer approval |
| B-007 | G-33 records for Gemini and Fireworks | 3, 9 | Draft PR; approves nothing |
| B-008 | Fireworks governance: reconcile docs, verify terms and model IDs | 3 | Not started |
| B-009 | Offline content-pack contract | 1, 5, 7 | Design to write |
| B-010 | Bounded agentic study planner design | 1, 4 | Design to write |
| B-011 | M3-D PRs 7 to 15 | 2 | In progress (own lane) |
| B-012 | M3-F implementation | 2 | In progress (own lane) |
| B-013 | Retrieval quality on real material | 4 | In progress (own lane) |
| B-014 | Offline benchmark harness and device procedure | 5, 8 | In progress (own lane) |
| B-015 | 100-task evaluation set (50 RAG, 30 orchestration, 20 question generation) | 3 | Not started |
| B-016 | GCP staging design and Terraform | 10 | In progress (own lane); spending needs authorisation |
