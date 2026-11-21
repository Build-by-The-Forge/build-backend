# BUILD Implementation Baseline

**Taken:** 2026-11-20T21:38Z (UTC snapshot), from `git fetch` of each repository's default branch and the open pull requests on GitHub at that moment. Anything after that time isn't in it. Lane statuses are dated, handover-based snapshots, not a live dashboard.

**Purpose:** Phase 0 of `docs/BUILD_IMPLEMENTATION_PLAN.md` (backlog B-001 to B-005). It records where the code stands, with the plan's completion states, and the documentation conflicts found.

**Rules for this document:**
- Every claim about code was read in the repository named, and cites a path.
- States are only those in plan section 9: implemented on main, merged (verification pending), open PR, design only, not started, blocked, deferred.
- It is a snapshot. `docs/milestone-register.md` and `contracts/mobile/gaps.yaml` stay the trackers.

## 1. Repositories (B-001)

Snapshot 2026-11-20T21:38Z.

| Repository | Default branch | Head at snapshot | Open PRs at snapshot |
|---|---|---|---|
| `build-backend` | `main` | `e9067ed` (merge of #115, 2026-11-15) | #116 plan and baseline, #117 PRD amendment (draft), #118 G-33 records (draft), #119 status refresh, #120 entitlement design (draft), #121 M3-D PR 7 backend (`claude/m3d-pr7-f68199`, ready), #122 offline content-pack contract (draft), #123 study-planner design (draft) |
| `ai-service` | `main` | `4150c5f` (merge of #65, the Gemini adapter, 2026-11-20). **#65 is merged; it is code only and enables nothing** | #66 M3-F tutor turn, #67 PRD mirror (draft), #68 G-18 chat returns only cited passages, #69 M3-D PR 7 AI dispatch scope, #70 `PROJECT_STATUS.md` (draft), #71 AI-12 offline benchmark harness (draft) |
| `Build-UI` | `main` | `30a869e` (2026-10-30, "Refine FUTA map styling…") | #4 typed API client with a drift check, #5 sign-in and protected routes, #6 onboarding and academic profile (M5, ready) |

Alembic head on `build-backend` main: `0032_s02_academic_profiles` (`alembic/versions/`). The next free revision is `0033`; the M3-D uploads lane owns it, and M3-F must ask before taking one.

## 2. Status by area (B-002)

### 2.1 build-backend

| Area | State | Evidence |
|---|---|---|
| Identity, sessions, registration (S-01, M3-B) | Implemented on main | Register M3-B: #75, #76. Mobile still doesn't call it |
| Academic profile (S-02) | Implemented on main | #111, migration `0032_s02_academic_profiles.py`; G-28 in `closed` of `contracts/mobile/gaps.yaml` |
| Catalogue reads and pagination (M3-C) | Implemented on main | #77 |
| Assessment lifecycle L1 to L3, M3-E gaps | Implemented on main; M3-E completion awaits the reviewer's check | Register |
| M3-D foundation: scope filter, read policy, provenance, classification, scanning | Implemented on main | #95, #99, #100, #103, #104, #106, #108 |
| M3-D student routes: upload, list, retry, bytes, delete, rights, shelf, publication (PRs 7 to 16 of `docs/m3-d-design.md`) | **Not implemented on main.** Implementation of PR 7 exists in open PRs: ai-service #69 (head `de4e5fc`) and backend #121 (head `801aa81`). PRs 8 to 16 are not started. (States used in this document: not merged into main; committed locally; pushed; opened as a PR.) | G-01, G-02, G-11, G-12, G-13, G-25, G-30, G-32, G-38, G-41 to G-43 still open |
| M3-F conversations | Design only plus contract (#90, #81, #83); no implementation | G-04, G-17 open; `docs/m3-f-design.md` |
| M4 retrieval eligibility and citation authorisation | Design only | `docs/mobile-m0-boundary.md`; G-05, G-31 open |
| Student journey contracts for S-03, S-07 to S-10, S-13, S-14 | Design only (#112 merged) | `docs/student-journey-contracts-design.md`; no contract operations yet |
| Entitlements | Not started | PRD §81, §84 |
| Offline authorisation lease and sync | Design only | `docs/m3-d-design.md`, approved at `ab09d2c` |
| Memory gate | Implemented on main, closed | `GATE_OPEN = False` in `app/core/learning_memory_gate.py`; L4 specified, not started |
| GCP staging | Not started on main; a lane exists with nothing committed | worktree `gcp-staging-a19c38` |

### 2.2 ai-service

Rows were read at `2c76c93` except the Gemini row, re-read at `4150c5f`.

| Area | State | Evidence |
|---|---|---|
| Model Gateway, one execution boundary (AI-01) | Implemented on main | `app/core/models/gateway.py`; chat, explain and questions through it (#56); legacy layer removed (#63) |
| Gateway providers on main | `openai`, `deterministic`, `mock` | `app/core/models/providers/{openai,deterministic,mock}.py` |
| Gemini adapter | Implemented on main, **not enabled** | Merged in #65 (`4150c5f`): `app/core/models/providers/gemini.py`; `GATEWAY_PROVIDERS` is `{openai, gemini}` and `MODEL_PROVIDER` accepts `gemini` (`app/core/config.py`). `MODEL_PROVIDERS_APPROVED` is empty by default, so the gateway fails closed for student passages until G-33 is approved. The adapter passes the key explicitly with `vertexai=False` |
| Fireworks adapter | Not started | No code; governance first (plan phase 3) |
| Provider approval | Implemented on main | `MODEL_PROVIDERS_APPROVED` and `GATEWAY_PROVIDERS` in `app/core/config.py`; empty by default |
| Ingestion and OCR | Implemented on main | `app/services/tasks/handlers.py`; `app/services/ocr` |
| Retrieval (pgvector, lexical, hybrid, evidence) | Implemented on main, quality gap | `app/services/rag/`; migration `c3e81f4a9d27_document_chunks.py`; real-material recall@5 62.5% per PRD §0.6 (not re-measured here) |
| Tutor turn route for conversations (M3-F AI side) | Not started on main | Lane `m3f-conversations` |
| Explain, question generation, trees, read | Implemented on main; partial against the capability map | `app/api/v1/ai/{explain,generate_questions,tree,read}.py` |
| AI-10 CBT exam | Implemented, grounded, unrouted | `app/services/generation/` (#61, #62); no route in `app/api/v1/ai/` |
| AI-10 topic-coverage check | Not on main; uncommitted lane work | handover note |
| Agents and tools | Implemented on main, not exposed | `app/services/agents/executor.py`; `app/core/tools/{registry,contracts,budget,validator}.py`; `app/services/tools/builtins/{content,curriculum,question}.py`. No `search_course_material` tool |
| Offline benchmark harness | Not on main; local WIP commit | handover note, branch `claude/ai-12-offline-benchmark-4620ed` |
| OCR corpus and real baseline | Not on main; branches unpushed | lane `p3-5-ocr-baseline` |
| Learning Memory | Implemented, gated off | `/v1/ai/memory/*` in `app/api/v1/ai/memory.py` |
| `PROJECT_STATUS.md` | Stale | Says 208 tests; rewritten in its own PR |

### 2.3 Build-UI (`mobile-app-main/`)

| Area | State | Evidence |
|---|---|---|
| Screens (auth, onboarding, dashboard, calendar, Read Mode, tutor, CBT, settings) | Implemented as prototypes, calling no backend | Register S-01 to S-14 rows; `src/app/` |
| Tutor screen | Prototype that calls an AI URL directly; must be removed | `src/app/dashboard/buildai.tsx` is the only file under `src` that uses `fetch` or `axios` |
| CBT screen | Fabricated result | `src/app/dashboard/cbtquiz.tsx:108` alerts "Your score is 95%." |
| Typed API client, token storage | Not started | M5 |
| Offline store, on-device runtime | Not started | |

## 3. Contract and gap snapshot (B-004)

From `contracts/mobile/gaps.yaml` on `e9067ed`: **20 closed, 23 open** (4 contract gaps, 19 implementation gaps). `contracts/mobile/openapi.yaml` has 55 `operationId` entries.

- Closed: G-03, G-06, G-08, G-09, G-10, G-14, G-15, G-16, G-20, G-21, G-22, G-24, G-27, G-28, G-29, G-35, G-36, G-37, G-39, G-40 (G-28 closed by #111).
- Open contract gaps: G-07, G-18, G-19, G-23.
- Open implementation gaps: G-01, G-02, G-04, G-05, G-11, G-12, G-13, G-17, G-25, G-26, G-30, G-31, G-32, G-33, G-34, G-38, G-41, G-42, G-43.

## 4. Lanes running now (B-005)

Snapshot 2026-11-20T21:38Z. Owners are the sessions on this machine. For each lane, **committed** means a commit exists on a local branch, **pushed** means the branch is on the remote, **opened** means a PR is open. Sources: `git ls-remote`, local branch heads, `gh pr list`, and hand-over notes.

| Lane | Work | Committed | Pushed | Opened |
|---|---|---|---|---|
| M3-D uploads (PRs 7 to 16) | build-backend `claude/m3d-pr7-f68199`; ai-service `feat/m3d-pr7-dispatch-scope` | Yes | Yes | Yes: build-backend #121, ai-service #69 (PR 7 only; PRs 8 to 16 not started) |
| M3-F tutor | ai-service `feat/m3-f-tutor-turn` | Yes | Yes | Yes: ai-service #66; the paired backend work isn't open |
| G-18 chat fix | ai-service `fix/g-18-chat-context` | Yes | Yes | Yes: ai-service #68 |
| Offline benchmark (AI-12) | ai-service `claude/ai-12-offline-benchmark-4620ed` | Yes | Yes | Yes: ai-service #71 (draft) |
| Retrieval quality and OCR baseline | ai-service `p3-5/ocr-corpus` (a local commit `397ce5f`) | Yes, locally | No remote branch found | No |
| AI-10 coverage | ai-service `claude/ai10-topic-coverage-60ec4e` | No commit beyond `main` found; the hand-over note says changes are uncommitted | No | No |
| GCP staging | build-backend `claude/gcp-staging-a19c38` | No (at `e9067ed`) | No | No |
| Gemini adapter | ai-service #65 | Yes | Yes | **Merged** (`4150c5f`); enables nothing |
| Mobile client (M5) | Build-UI `m5/typed-api-client`, `m5/auth-session`, `m5/onboarding-profile` | Yes | Yes | Yes: Build-UI #4, #5, #6 |
| Plan and governance (this lane) | build-backend `docs/*` and ai-service `docs/*` branches | Yes | Yes | Yes: build-backend #116 to #120, #122, #123; ai-service #67, #70 |

## 5. Documentation conflicts (B-003)

| # | Conflict | Where | Proposed resolution |
|---|---|---|---|
| 1 | **Provider.** PRD §0.2 and §38 and `docs/build-production-blueprint.md` §2 name Gemini as the only online provider. `ai-service/README.md` says `MODEL_PROVIDER=openai` (default) or `deterministic`. The code agrees with the README (`app/core/config.py`: `MODEL_PROVIDER: Literal["openai", "deterministic"] = "openai"`). The plan adds Fireworks, under governance | PRD, blueprint, README | PR B marks the PRD's provider section "under reconciliation: Gemini plus Fireworks pending G-33 and reviewer approval". README is corrected when #65 lands |
| 2 | **Offline CBT.** PRD §146.6 lists taking CBTs offline and recording progress locally. Resolved by the user on 2026-11-20: official CBT is online-only in R1 and R2; offline practice exists only in R2 and only if separately approved, with provisional scores until server validation | PRD §0.1 item 10, §93, §146.6 | PR B |
| 3 | **Offline AI and offline packs as v1.** PRD §0.6 item 7 and §0.1 make offline generative AI and offline use production acceptance conditions. Resolved 2026-11-20: managed offline packs, the lease, sync, offline retrieval and offline AI are R2; R1 has limited caching of already-opened documents | PRD §0.1, §0.4 step 6, §0.6 | PR B (reviewer approval) |
| 4 | **Offline model list.** PRD §146.3 names Qwen3-1.7B, Qwen3-0.6B, "Glimmer 2B", Gemma 3 1B and SmolLM2-1.7B. The plan's targets are Qwen3.5-0.8B, Qwen3-1.7B and SmolLM2-1.7B. "Glimmer 2B" is **unverified as a benchmark candidate**: the AI-12 hand-over note records finding only a 30B model of that name, but that is a hand-over note, not a model-card verification. The exact repository and checkpoint must be confirmed before it is included | PRD §146.3, ai-service README | PR B |
| 5 | **The 2026-11-07 blueprint is stale.** It lists AI-01 as Partial with two abstractions (gone since #56 and #63), AI-10 as "Not reachable" with no structure, ai-service main as `2506dfd`, 24 open gaps, and S-02 as missing | `docs/build-master-execution-blueprint.md` | The status refresh PR |
| 6 | **Register.** Its gap counts (20 closed, 23 open) match `gaps.yaml`, but it records none of #110 to #115 (S-02, the journey design, the dependency fix, the encrypted-PDF message) and nothing about the running lanes | `docs/milestone-register.md` | The status refresh PR |
| 7 | **`PROJECT_STATUS.md`** in ai-service: no pgvector and no task queue, 208 tests. The code has pgvector (`c3e81f4a9d27_document_chunks.py`) and a task worker (`app/services/tasks/`) | ai-service | Its own PR |
| 8 | **Gemini 3.8 Flash and Fireworks model names.** The PRD names Gemini 3.8 Flash as the production target; the plan's models (Nemotron 3.5 Lightning 30B A3B, gpt-oss-120B, DeepSeek V4.1 Flash) come from a page this lane couldn't read. None is verified | PRD §0.2, plan | G-33 records (PR C) verify or flag each |
| 9 | **PRD copies.** The PRD exists in `build-backend` and `ai-service` and is meant to be identical | both | PR B edits both identically |
| 10 | **App size and platform requirements** (Android 14+, 4 GB RAM, under 100 MB, English only) appear in no PRD section | plan section 3 | PR B records them |
| 11 | **Fireworks as a second provider.** A research report ("BUILD — Provider and Agentic Architecture Model", Notion, 2026-11-18, relayed by the review session; this lane did not read the page) proposes Gemini for high-scale work and Fireworks for all small and medium work. PRD §0.2, §38, §39 and the production blueprint make Gemini the online provider. The report is a proposal, not a governance record. Resolved 2026-11-20: Gemini is the designated first R1 provider but is not enabled for student or institutional passages until its G-33 is approved, and the gateway fails closed until then; Fireworks is proposed and disabled until its own governance and evaluation are satisfied | PRD §0.2, §0.4, §38 to §41, §110, §146.9 to §146.10 | PR B section 0.9 and the plan's section 14 |
| 12 | **G-33 covers Gemini only.** A second provider needs a separate record | `contracts/mobile/gaps.yaml` G-33 | PR C |
| 13 | **Offline model portfolio.** The report names one offline model (Qwen3-1.7B) for "Tier 0" offline reading and flashcards, shipped before agentic work. The plan has three targets, roles assigned only after benchmarking, and offline AI in R2 | PRD §146.3 | PR B |
| 14 | **Entitlement model.** The report proposes BUILD absorbing the small tier and schools paying for medium via quota. PRD §78 to §88 define Free, Plus, Pro, Campus with backend-authoritative budgets. Resolved 2026-11-20: a provisional plan-to-capability table (Free restricted online tutor; Plus adds offline AI; Pro adds agentic study workflows), model tier and agentic capability as separate entitlements, Campus left undefined, no per-token student billing | PRD §78 to §88 | The plan's section 14.2 and `docs/entitlement-design.md` |
| 15 | **Fallback models.** The report names GLM, Qwen and MiniMax as fallbacks outside its own default portfolio. Resolved: fallback only within approved portfolio entries | The report | The plan's section 14.1 |
| 16 | **Circuit breaker.** The report says three failures, then five minutes. The gateway already has a breaker and retry policy (`app/core/models/resilience.py`) | `ai-service` | Keep the gateway's as the baseline; make thresholds configurable and set them from measurements (plan §14.4) |
| 17 | **Identifiers in provider prompts.** The report says send anonymised IDs. Pseudonymous data can still be personal data, and a student's own text can contain personal data | G-33 | Plan §14.3; each G-33 record states it separately |
| 18 | **Cached documents versus immediate denial.** `docs/m3-d-design.md` promises immediate denial on revocation; a copy cached on the device would outlive it | M3-D, plan §2.3 | Decision: R1 ships without a document cache unless an approved policy and its evidence exist |

## 6. What this baseline does not establish

- It ran no tests. Pass counts, coverage and CI state are not claimed except where a PR's hosted CI is cited.
- Retrieval quality figures are the PRD's, not re-measured.
- Lane states come from hand-over notes and `git worktree list`; a lane's branch may have moved since.
- Build-UI was read for structure and two files; its tests were not run.
