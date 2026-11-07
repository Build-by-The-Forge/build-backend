# BUILD Master Execution Blueprint

**Status:** proposed, for the reviewer. **Baseline:** 2026-11-07, `build-backend` main `a8f4b4d` (after #108), `ai-service` main `2506dfd` (after #46), and `Build-UI` main `9c6937c`.

**Purpose:** the source of truth for the delivery programme. Every claim about existing code below was checked against the repository it names.

**Scope:**
- the complete AI Service;
- the complete student journey;
- the mobile application (`Build-UI`, `mobile-app-main/`);
- the production foundation under all three.

**Not in scope:** login experiences for any persona other than students. Internal service authentication, backend authorization and controlled operator commands stay. They are system security, not user logins.

## 1. Rules that hold throughout

| Rule | Where it's enforced |
|---|---|
| The backend owns the public API, identity, tenancy, authorization and academic truth | `build-backend` |
| The AI service owns intelligence and retrieval, and is called only by the backend, signed | Service Signature v1, both directions |
| Mobile is a client of the backend only. It never calls the AI service and never decides permissions, scores, entitlements or grounding | `Build-UI` |
| `GATE_OPEN = False`; Learning Memory stays disabled until its gate is approved | Both services' settings and startup checks |
| No production provider receives student or institutional passages until G-33 is approved | Provider configuration plus a release gate |
| No document is processed before a clean malware scan | #106: quarantine on insert, job gate, fenced verdict |
| Unknown-scope and pending-lowering documents are excluded from retrieval | AI scope filter, `denied_assets` (#104) |
| No answer is returned without provenance checked against current read permissions | #100 |
| CBT attempts, scores and release are backend-authoritative | M3-E, L1 to L3 |
| No backfill of older documents until the revocation and outbox path is deployed and verified | Reviewer's ruling, 2026-11-07 |

## 2. Baseline

### Merged in this round

| PR | What | Merged on |
|---|---|---|
| #95 | Migration 0030: ownership, rights, blobs, the one-active-job index | CI and boundary gate green |
| #96, #97 | M3-E pagination (G-10) and response fields (G-39) | CI and boundary gate green; #97 after #102 |
| #98, #105 | Base image 3.13.18; pinned zlib security update | Production image scan clean |
| #99, #100 | The one read policy; the provenance check (`ANSWER_WITHHELD`) | CI and boundary gate green |
| #101 | `ACTIVE_JOB_EXISTS` convention | Docs |
| #102 | Catalogue course lock (the lost-write fix) | Race test 40 of 40 |
| #103, #104, #108 | Migration 0031; classification, outbox, dispatcher, immediate denial; per-decision authority recheck | CI and boundary gate green, including the real worker-to-AI dispatcher test |
| #106 | Malware scanning, quarantine and the scan gate | CI and the **real-ClamAV** boundary gate green |
| `ai-service` #46 | README: the ingestion pipeline as built | CI green |

### Open

None in the merge queue. This document (#107) is the only open PR.

### Carried forward from the reviewer

- **#104, done by #108:** each applied decision rechecks the tenant authority and the operator's membership inside its own transaction, holding both rows `FOR SHARE` until it commits. A revocation or demotion during a run waits for the decision in flight, and stops every later decision.
- **#99:** the read policy doesn't complete scanning. #106 does, and PR 10's byte route must refuse `quarantined` and `rejected` documents to everyone.
- **#106:** the scan stand-in stays confined to tests that aren't about scanning. `real_scanning` tests and the boundary gate keep exercising the real lifecycle.
- **Backfill:** older documents stay unavailable for processing until a controlled backfill scans them and handles rejected or already-indexed ones through the outbox.

## 3. AI Service: capability map

**Status key:**
- **Built:** implemented, reachable and tested.
- **Partial:** implemented, but missing something the milestone requires.
- **Placeholder:** a route that returns a fixed message.
- **Not started:** no code.

| # | Capability | Existing code (`ai-service`) | Status | What's missing |
|---|---|---|---|---|
| AI-01 | Model Gateway | `core/models/gateway.py`: retries, circuit breaker, token-bucket rate limit, budget, fallback. Providers in `core/models/providers/`: `openai`, `mock` | **Partial** | **Two abstractions:** chat, explain and question generation call `services/ai/llm.py` (`LLMProvider`, OpenAI or deterministic) directly, not the gateway. Only `services/agents/executor.py` uses the gateway. Consolidate onto the gateway, then add the Gemini adapter, with the model ID verified and G-33 enforced in configuration |
| AI-02 | Ingestion and OCR | `services/tasks/handlers.py` `ContentIngestionTaskHandler`: verified fetch, then text layer or OCR (`services/ocr`: PaddleOCR, OpenVINO), page-aware chunks, ONNX MiniLM embeddings, one-transaction durable index, signed stage callbacks | **Built** | Harden, don't rewrite: OCR edge cases, tables and equations, versioning and reprocess, index consistency after deletion and revocation, duplicate and retry behaviour, concurrency. `/v1/ai/ocr` is a **placeholder** route to remove or implement |
| AI-03 | Retrieval and RAG | `services/rag`: pgvector store, lexical full-text, hybrid `retrieval.py`, `evidence.py`, `recorder.py` (`sources_used`), `scopes.py`, index fence; `/v1/ai/retrieve` | **Built**, quality gap | Real FUTA material scored 62.5% recall@5 (tier-2). Separate the variables: extraction, chunking, metadata, hybrid weighting, reranking. Allow-list retrieval for personal documents (M4, G-05) |
| AI-04 | AI Tutor | `services/ai/orchestrator.py` `chat`: grounded with `check_grounded`, abstains without evidence, signed `sources_used` | **Partial** | Conversations (M3-F, contract #90): multi-turn history, citations with excerpts, the redacted flag, `TURN_IN_PROGRESS`. Backend G-04, G-17, G-18 |
| AI-05 | Explanation Engine | `orchestrator.explain`, `generation/explain.py`, `/v1/ai/explain` | **Partial** | Depth levels (structured explanations at selectable depth), and an evaluation set |
| AI-06 | Question generation | `generation/question_gen.py`, `structured_questions.py`, `question_checks.py`, `/v1/ai/generate-questions` | **Partial** | Grounding in the student's authorised course material; a student practice route on the backend; difficulty calibration; generated questions labelled distinct from official ones |
| AI-07 | Knowledge Trees | `services/tree/generator.py`, `/v1/ai/tree/generate` | **Partial** | It builds a tree from a supplied title and topic list only. It must be generated from authorised course material, grounded, with provenance and persisted progress |
| AI-08 | Read Mode | `services/tree/learning_path.py`, `/v1/ai/read/start` | **Partial** | A path from a supplied root only. Needs grounded summaries, checkpoints, and the backend byte route (PR 10) for the document itself |
| AI-09 | Learning Memory | `services/memory/memory_service.py`, `reward.py`, `/v1/ai/memory/*` | **Built, gated** | Stays off until its gate (retention, enforcement, deletion, controls, idempotency, consent) is approved. L4 carries the remaining conditions |
| AI-10 | Fusion Exam Intelligence | `generation/fusion_engine.py`, using `adaptive_engine` and `cbt_ai_generator` | **Not reachable** | Code exists; no route uses it. Needs a contract, inputs from assessment history (backend-authoritative), and an evaluation |
| AI-11 | Adaptive difficulty | `generation/adaptive_engine.py` | **Not reachable** | As AI-10; it depends on evaluated evidence of difficulty |
| AI-12 | Offline AI | None in this repository | **Not started** | On-device portfolio (Qwen3-1.7B, smaller fallbacks, Glimmer in the benchmark), benchmarked on target Android devices before any claim |
| AI-13 | Evaluation and observability | Retrieval quality gate in CI, tier-2 evaluation tooling, Prometheus metrics, the worker's task metrics | **Partial** | Grounding, citation correctness, latency and cost dashboards per capability; a per-capability evaluation set with a baseline before any threshold |
| AI-14 | Security and governance | Service Signature v1, signed responses, single-use nonces, the scope filter, `denied_assets`, `sources_used`, the memory gate, the ownership manifest | **Partial** | Provider data-processing records (G-33), retention and deletion of derived data (G-32), and an audit of provider calls |
| — | `/v1/ai/generate` | Placeholder route | **Placeholder** | Remove, or define it under a capability above |

### AI implementation order

1. **AI-01 consolidation.** The orchestrator, explain and question generation move onto `ModelGateway`; `LLMProvider` is retired. Behaviour is unchanged, so existing tests and the deterministic provider still pass.
2. **AI-01 Gemini adapter**, behind the gateway:
   - the model ID is verified at startup against the provider;
   - **disabled for passages** until G-33 is recorded;
   - free models for development and tests, as agreed.
3. **AI-04 conversations**, the M3-F implementation, paired with the backend.
4. **AI-03 quality:** the tier-2 variables one at a time, with the baseline recorded first.
5. **AI-07 and AI-08 grounded in course material**, then **AI-06** practice grounded in the same material.
6. **AI-10 and AI-11**, once assessment history is exposed to them by the backend.
7. **AI-13 throughout;** **AI-12** as a separate benchmark track; **AI-09** behind its gate.

## 4. Student journey: endpoint, AI and screen

**Contract column:**
- **In contract:** in `contracts/mobile/openapi.yaml`.
- **Not designed:** has no contract yet and needs a contract PR first.

**Backend status:** "Implemented" means it serves the contract today. Gaps are numbered from `contracts/mobile/gaps.yaml`.

**Mobile column:** the screen as it is today. "Prototype" means it renders but calls no backend.

| # | Capability | Backend endpoints | Contract | Backend status | AI interaction | Mobile today | Next work |
|---|---|---|---|---|---|---|---|
| S-01 | Register, login, logout, sessions | `/identity/*` (12 routes) | In contract | **Implemented** (M3-B) | None | `(auth)/login`, `signup`, `preauth`: prototype; Sign In skips authentication | Mobile: API client, secure token storage, single-flight refresh ([refresh contract](mobile-api-conventions.md)) |
| S-02 | Academic onboarding | `/tenants/{slug}/join`, `/identity/memberships`, `/catalogue/faculties`, `departments`, `programmes`, `courses` | In contract, except saving a student's programme and courses | Join and catalogue implemented; **no record of the student's programme, department or courses** (G-28) | None | `(onboarding)/step-one` to `five`: local context only | Backend: design and implement the academic profile (programme, level, enrolled courses). Mobile: wire onboarding to it |
| S-03 | Dashboard | None | Not designed | **Missing** | Optional recommendations later | `dashboard/home`: fixture data | Contract: a dashboard summary built from courses, recent activity, attempts and documents |
| S-04 | Study Shelf | `/content/my-documents` (list, get, patch, delete) | In contract | **Missing** (G-01, G-41, G-32) | None | `services/studyShelf.ts`: local only | Backend PR 8. Mobile: local shelf stays distinct from server documents |
| S-05 | Upload | `POST /content/my-documents`, `.../retry` | In contract | **Missing** (G-01, G-02, G-38, G-11, G-12, G-25); scanning in #106 | Ingestion | Document picker exists, local only | Backend PR 7 and 8 (and 9 for retry); mobile upload with real statuses |
| S-06 | AI Tutor | `/ai/conversations/*` | In contract (#90) | **Missing** (G-17, G-04, G-18); `/ai/chat` exists outside the contract | Chat, citations, provenance | `dashboard/buildai`: calls an AI URL directly; **must be removed** | M3-F backend and AI PRs; mobile chat on conversations |
| S-07 | Read Mode | `GET /content/assets/{id}/content`, plus a reading state | Bytes in contract; reading state not designed | **Missing** (G-13) | AI-08 | `dashboard/readmode`: static text | Backend PR 10 (ranges, `nosniff`, scan refusal); a reading-state contract |
| S-08 | Knowledge Trees | None | Not designed | **Missing** | AI-07 | None | Contract plus a backend route over AI-07 |
| S-09 | Study planning | None | Not designed | **Missing** | Recommendations later | `dashboard/calendar`: local events, works | Contract for goals and schedules; local calendar events stay local |
| S-10 | Practice | None for students (`/ai/generate-questions` needs a staff permission) | Not designed | **Missing** | AI-06 | None | Contract: student practice sets from authorised material, kept apart from official CBT |
| S-11 | CBT | `/assessment/assessments*`, `/assessment/attempts*` (11 routes) | In contract | **Implemented** (M3-E, L1 to L3); G-39 in #97 | None | `dashboard/cbtquiz`: hardcoded, fabricated 95% | Mobile: real attempts, answers, submit; remove the fabricated score |
| S-12 | Results | `/assessment/attempts/{id}/result` | In contract | **Implemented** (release policy, feedback timing) | Explanations later (AI-05) | None | Mobile results screen |
| S-13 | Progress analytics | None | Not designed | **Missing** | AI-10 and AI-11 later | None | Contract: aggregates over verified attempts and activity |
| S-14 | Settings | `/identity/change-password`, `logout-all` | Partly in contract | Account controls implemented; preferences and notifications missing | None | `dashboard/settings`: local | Contract for preferences |

**Subscriptions** (Free, Plus, Pro, Campus) are backend-authoritative and come after S-01 to S-14. They are not designed yet.

## 5. Integration contracts

| Boundary | Contract | State | Owner |
|---|---|---|---|
| Mobile and backend | `contracts/mobile/openapi.yaml`, with `gaps.yaml` enforced by the drift gate | 53 operations; 26 gaps open | Backend, one contract PR per milestone |
| Backend and AI, requests | Service Signature v1, user or system context, single-use nonce | Built, boundary-tested | Paired PRs; the boundary gate runs against `ai-service` main |
| Backend and AI, responses | Signed response with `sources_used`, then the provenance check (#100) | Built | Paired |
| Backend and AI, scope | `/v1/ingest/scope-assignments`, versioned, plus `denied_assets` | Built; the dispatcher in #104 | Paired |
| Backend and AI, ingestion | Signed dispatch, stage callbacks, the reconcile pull | Built; dispatch scope in PR 7 | Paired |
| Mobile and AI | **None, by design** | — | — |

**Needed first:** a **student journey contract** extending the mobile OpenAPI with S-02 (the academic profile), S-03, S-07 (reading state), S-08, S-09, S-10, S-13 and S-14. Each operation names its authorization, its AI interaction if any, and its acceptance test. Mobile builds against it, with deterministic mocks only in development and a production build that refuses mock mode.

## 6. Delivery stages

Stages overlap. Each PR states its exit evidence.

| Stage | Backend | AI service | Mobile | Exit evidence |
|---|---|---|---|---|
| **0. Stabilise** | Merge #97, #104, #106; the #104 per-decision authority follow-up | — | Baseline audit (plan M0) | Clean mains; CI and boundary gates green |
| **1. Contracts** | Student journey contract PR (S-02, S-03, S-07 to S-10, S-13, S-14); academic profile design | AI-01 consolidation PR | Typed API client from the contract; mock adapters; route protection | Contract merged and drift gate green; mobile typechecks against it |
| **2. Student foundation** | Academic profile (migration), dashboard summary | — | Auth, onboarding and dashboard wired | A real student registers, onboards and sees their courses on a device |
| **3. Secure content** | PR 7 (dispatch scope), PR 8 (upload, quotas, list and get), PR 9 (retry), PR 10 (bytes), controlled backfill | AI-02 hardening | Upload, the shelf, Read Mode bytes | Upload, then quarantine, scan, ingest, ready, then read on a device; EICAR rejected |
| **4. AI foundation** | M3-F conversations; provider configuration | AI-01 Gemini (passages off until G-33), AI-04 | AI Tutor with citations | A grounded answer with verified citations; a revoked source withholds it |
| **5. Learning intelligence** | Routes for trees, read state and practice | AI-07, AI-08, AI-06 grounded; AI-05 depth | Trees, Read Mode, practice | Each grounded with provenance; generated questions labelled |
| **6. Assessment intelligence** | Progress aggregates | AI-10, AI-11 from backend history | CBT and results wired; progress | The learning-to-assessment loop on real data |
| **7. Personalisation** | Gate conditions (L4) | AI-09 behind its gate | Memory UI behind a flag | Gate decision recorded; nothing enabled before it |
| **8. Offline** | Authorization lease and sync (design #79) | AI-12 benchmark harness | On-device runtime | Per-device acceptance results |
| **9. Hardening** | Deployment (GCP), monitoring, backups, restore drill | Evaluation dashboards | Accessibility, Android release, end-to-end tests | Production release evidence |

## 7. Test ownership

| Layer | Where | Owner |
|---|---|---|
| Unit and integration | Each repository's CI | The PR's author |
| PostgreSQL behaviour (races, constraints, generic plans) | `build-backend/pg_smoke`, `ai-service` PostgreSQL tests | The PR's author |
| Cross-service | `build-backend/boundary` (real AI service, real ClamAV, object storage, Redis) | Paired PRs |
| Contract drift | `test_mobile_contract_drift.py` and `gaps.yaml` | The backend contract owner |
| AI quality | Retrieval quality gate, tier-2 evaluation, per-capability sets | The AI service |
| Mobile | Typecheck, lint, unit, component and end-to-end tests (plan section 9) | Mobile |
| Student journey acceptance | One end-to-end suite against deployed services, from registration to results | Integration lane |

## 8. Gates

| Gate | Opens when | Until then |
|---|---|---|
| Learning Memory (`GATE_OPEN`) | Retention, enforcement, deletion, controls, idempotency and consent are approved | Code is built and tested behind it; off everywhere |
| External AI processing (G-33) | The provider's processing, retention, training, sub-processor and deletion terms are recorded and approved | The Gemini adapter can be built and tested with non-student text only |
| Document processing | A clean scan per document (#106) | Quarantined |
| Retrieval of a document | Its institutional scope is acknowledged by the AI service, and it isn't denied | `unknown`, or excluded |
| Older documents | The outbox path is deployed and verified, then a controlled backfill | Unavailable for processing |
| Offline AI | Device benchmarks pass | Not offered |
| Subscriptions | Backend entitlements implemented | No feature depends on a client flag |
| Other personas | Out of this delivery | Student login only |

## 9. Decisions for the reviewer

1. **The academic profile (S-02).** I propose a backend-owned student profile: programme, level and enrolled courses, validated against the catalogue, closing G-28. It would be a migration after 0031, and its own design PR first.
2. **Practice versus CBT (S-10).** I propose that generated practice never becomes an official assessment: separate tables or labels, never scored as CBT, never in results.
3. **AI-01 order.** Consolidate onto `ModelGateway` before adding Gemini, so Gemini plugs into the resilience, budget and fallback layer instead of into `LLMProvider`.
4. **The placeholder routes** `/v1/ai/ocr` and `/v1/ai/generate`. I propose removing them (ingestion already OCRs) rather than implementing them.
