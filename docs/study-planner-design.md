# Bounded agentic study planner (DRAFT design spec)

**Status: draft design for the reviewer. Release 2** (plan section 2.2). Release 1's tutor is naive RAG only, with no autonomous multi-hop retrieval, no reading paths and no agentic loops. This design authorises no route, tool, provider or code, and enables no Fireworks model.

**Builds on, and changes none of:**
- the agent runtime in `ai-service` (`app/services/agents/executor.py`, `app/core/agents/`) and the tool plane (`app/core/tools/`, `app/services/tools/`);
- the Model Gateway (`app/core/models/`, design `docs/ai-01-model-gateway-design.md`);
- the evidence rule (`app/services/rag/evidence.py`), the offline contract (`docs/offline-content-pack-contract.md`) and the entitlement design (`docs/entitlement-design.md`);
- PRD §0.3 and §26.1 (Naive and Agentic RAG routing).

**What it is:** the typed tool registry the planner may use, the loop it follows, how a request is routed between naive and agentic RAG, and how the same tools run online and offline. **What it is not:** an unrestricted agent. It has no database access, no free web access, and no authority over scores, mastery, permissions or tenant isolation.

## 1. What exists today (checked, `ai-service` `2c76c93`)

| Piece | Where | What it gives |
|---|---|---|
| Bounded agent loop | `app/services/agents/executor.py` (`AgentExecutor`) | A reasoning loop with hard ceilings. `AgentExecutionPolicy` (`app/core/agents/contracts.py`): `max_steps` 10, `max_model_calls` 10, `max_tool_calls` 10, `max_tokens` 8192, `max_cost_usd`, `max_runtime_seconds` 60, `max_consecutive_failures` 3, `max_output_bytes` 262,144 |
| Run state and events | `AgentRun`, `AgentState` (`COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `BUDGET_EXCEEDED`, `MAX_STEPS_EXCEEDED`), `AgentEventType` (`app/core/agents/events.py`: step, model-call and tool-call started and completed, plus terminal events) | The audit trail |
| Agent definitions | `AgentDefinition` with `allowed_tools`, `required_permissions`, `allow_proposals`, `allow_mutating=False` | A run is limited to named tools |
| Tool definitions | `ToolDefinition` (`app/core/tools/contracts.py`): name, version, `input_schema`, `output_schema`, `required_permissions`, `required_capabilities`, `tenant_scoped`, `side_effect` (`READ_ONLY`, `ANALYTICAL`, `PROPOSAL`, `MUTATING`), `timeout_seconds`, `max_invocations` | Schema, permission, timeout |
| Tool policy | `ToolExecutionPolicy`: `max_tool_calls`, `max_runtime_seconds`, `max_input_bytes` 64 KB, `max_output_bytes` 256 KB, `allow_proposals`, **`allow_mutating=False` ("strictly False by default in AI Service")** | Budgets, and no mutation |
| Authoritative context | `ToolContext` and `AgentContext`: `tenant_id`, `permissions`, `capabilities`, `deadline`, `denied_assets`; "cannot be modified or escalated by tool arguments or LLM outputs" | The caller's identity comes from the signed backend call, not the model |
| Budget tracking | `ToolBudgetTracker` (`app/core/tools/budget.py`), `ToolValidator` (`app/core/tools/validator.py`), `ToolRegistry` | Pre-invocation checks; input and output validation |
| Structured failures | `ToolResult` (`error_code`, fixed `error_message`, `retryable`); run results carry a fixed message, never exception text (#57, #59) | No leaked internals |
| Tools registered today | `content.search` (`READ_ONLY`, needs `content:read`, 15 s, refuses when `denied_assets` is `None`), `curriculum.lookup` (`READ_ONLY`, `curriculum:read`, 10 s), `draft.question` (`PROPOSAL`, `assessment:generate`, 20 s) (`app/services/tools/builtins/`) | Three tools |
| Not reachable | No route runs an agent: `app/main.py` mounts none | The runtime is built and unexposed |

**Consequence:** most of the design is configuration and new tool definitions on a runtime that already enforces the hard limits. The new work is the registry entries, the routing policy, the planner's definition, and the backend operation for progress.

## 2. Principles

1. **No unrestricted agent.** A planner run is an `AgentDefinition` with a fixed `allowed_tools` list, a fixed policy and a deadline. It can't add a tool, widen a scope or raise a budget.
2. **No database access from tools.** A tool receives data through the retrieval engine (which applies the scope filter and `denied_assets`) and through inputs the backend supplied in the signed call. No tool holds a database session or a connection string.
3. **The backend decides authority.** Scores, mastery, permissions, entitlements and tenant isolation are the backend's. The planner proposes; the backend applies, or refuses.
4. **Same grounding as the tutor.** Anything the planner says about course material cites retrieved passages and is checked by `check_grounded`; otherwise `NOT_COVERED`.
5. **Bounded, auditable, cancellable.** Every run has ceilings, an event trail, a deadline and a cancel path.
6. **The same tools online and offline.** One schema per tool, two executors (section 7).

## 3. The typed tool registry

Each tool below is a `ToolDefinition`. The table gives the planner-facing contract. "Permission" is a `required_permission`; "Budget" is the per-call share of the run's budget; "Audit" is what the event trail records (ids and counts, never student text).

| Tool | Purpose | Side effect | Permission | Timeout | Output |
|---|---|---|---|---|---|
| `search_course_material` | Retrieve passages from the student's authorised course material for a query and scope | `READ_ONLY` | `content:read` | 15 s | `{passages: [{number, chunk_id, document_id, page_start, page_end, excerpt, run_number, attempt}], sources_used}`. Wraps the existing `content.search` |
| `explain_concept` | A grounded explanation of one concept at a stated depth, from retrieved passages | `ANALYTICAL` | `content:read` | 30 s | `{explanation, citations, grounded}`; `grounded` false with `NOT_COVERED` when no valid citation |
| `generate_practice` | Draft practice questions from retrieved passages, labelled generated and distinct from official CBT | `PROPOSAL` | `assessment:generate` | 30 s | `{questions: [{stem, options, answer_key, source_passage, label: "generated"}]}`. Wraps `draft.question`. Never creates an official attempt |
| `evaluate_response` | Judge a student's practice answer against the answer key and the source, with feedback | `ANALYTICAL` | `content:read` | 20 s | `{correct, feedback, cited_passages}`. A provisional signal for the planner; **never a score of record** |
| `identify_knowledge_gaps` | Rank topics where the student's recent practice evidence is weak | `ANALYTICAL` | `progress:read` | 15 s | `{gaps: [{topic_id, evidence_count, weakness}]}`, computed only from the evidence the backend supplied in the request |
| `create_study_plan` | Turn gaps, a deadline and the course material into a dated plan | `PROPOSAL` | `plan:propose` | 30 s | `{plan: [{date, topic_id, activity, source_refs, minutes}]}`; a proposal the student must approve |
| `recommend_next_activity` | Choose the next step from the plan and recent evidence | `ANALYTICAL` | `plan:read` | 10 s | `{activity, reason, source_refs}` |
| `update_learning_progress` | Propose a change to the student's recorded progress | `PROPOSAL` (never `MUTATING`) | `progress:propose` | 10 s | `{proposal_id, change, evidence_refs}`; **applied only by the backend** (section 3.2) |

Names are proposals, and so are the permissions other than the three already registered (`content:read`, `curriculum:read`, `assessment:generate`): `progress:read`, `progress:propose`, `plan:read` and `plan:propose` don't exist yet. The first, `search_course_material`, replaces the registered name `content.search` or wraps it; the existing `curriculum.lookup` stays as a read-only support tool.

### 3.1 What every definition carries

`name`, `version`, `description`, `input_schema` and `output_schema` (JSON Schema; `ToolValidator` today checks input and the size of input and output payloads, and in `ToolDefinition` `output_schema` is optional, so requiring and validating an output schema is a proposal), `required_permissions`, `required_capabilities` (e.g. `agentic_workflows`, `model_tier:medium`), `tenant_scoped: true`, `side_effect`, `timeout_seconds`, `max_invocations`, and `is_enabled`. *Proposed:* a tool without an output schema isn't registered. Each tool also declares its **budget cost**: calls, an expected token range and a cost estimate, so a plan can be checked against the run's ceiling before it starts.

### 3.2 `update_learning_progress`, the only tool that touches progress

- **It cannot mutate.** The AI service policy has `allow_mutating=False`, and this tool is a `PROPOSAL`. It returns a proposal: what to change and the evidence (`source_refs`, practice-result ids).
- **The backend applies it, through an authorised operation.** The run's result reaches the backend in the signed response. The backend checks that the student's entitlement allows it, that the evidence refers to real practice rows, and that the change is within the rules for progress (never a score of record, never mastery set by the model). It then applies the change through its own operation and returns the outcome. A proposal the backend refuses is dropped and logged.
- **Mastery and official scores aren't reachable.** Progress here means planner state (plan items done, topics reviewed, practice taken). Authoritative mastery and assessment scores stay backend-computed from verified attempts.
- **Offline:** the proposal is queued on the device and sent at sync, where the backend validates it. Until then it is provisional (section 7).

## 4. The BUILD Intelligence Loop

One loop, five stages. Each stage names the tools it may call and the check that closes it.

| Stage | What happens | Tools | Closes with |
|---|---|---|---|
| **1. Understand** | Classify the request, resolve the course scope from the student's profile, and decide the route (section 5) | none (a model call, or a rule) | A route and a scope. Out-of-scope or unauthorised: refuse |
| **2. Plan** | For an agentic route, produce a short step list within the run's budget. For naive, skip | none | A plan the executor validates against `allowed_tools` and the ceilings; too big a plan is cut down or refused |
| **3. Retrieve and verify** | Retrieve passages; judge whether they suffice; retrieve again only if needed, within `max_tool_calls` | `search_course_material` | Evidence the recorder holds. If insufficient after the allowed iterations: `NOT_COVERED` |
| **4. Teach and practise** | Explain, or draft practice, from the evidence | `explain_concept`, `generate_practice` | `check_grounded`: cited and only cited, or abstain. Generated questions labelled |
| **5. Evaluate and adapt** | Judge the student's answers, find gaps, plan, recommend, and propose progress | `evaluate_response`, `identify_knowledge_gaps`, `create_study_plan`, `recommend_next_activity`, `update_learning_progress` | Backend validation of proposals; the student approves plans |

Stage 3 is the evidence stage and is never skipped. Stages 4 and 5 may loop back to 3, bounded by `max_steps`.

## 5. Routing: Naive RAG and Agentic RAG (PRD §26.1)

### 5.1 The policy

| Request | Route |
|---|---|
| Define a concept; summarise a note; explain from the student's material; generate questions from a chapter | **Naive RAG** (one retrieval, one generation, citation check) |
| Compare two sources; find contradictions; research across authorised sources; build a revision plan from weak areas | **Agentic RAG**, bounded, with controlled tools and student-approved context |

Naive is the default. A request routes to agentic only when **all** hold:
1. The request matches an agentic class in the table.
2. The student's entitlement resolves `agentic_workflows` (Pro, R2; `docs/entitlement-design.md`). Without it the request is **answered naively, or declined with an honest message**, never silently run as an agent.
3. The reservation for the run fits the student's budget.
4. The evaluation gate for that class has passed (section 9).

The route is chosen by a rule table first, and a model classification only to break ties, so routing is cheap and testable. The policy is configuration owned by the Platform Operations Layer (PRD §26.1), evaluated for cost, latency and quality, and **never a reason to skip grounding**.

### 5.2 R1 versus R2

In R1 the route is always naive. The code path for agentic stays off: no agent is exposed on any route, and the backend's AI request carries no `agentic` capability. R1's tutor is bounded: naive RAG only.

## 6. Bounds, budgets and cancellation

- **Ceilings** are the `AgentExecutionPolicy` fields above; a planner definition sets them lower than the defaults for its class (proposal: `max_steps` 6, `max_tool_calls` 8, `max_runtime_seconds` 45; to be set from measurement, section 9).
- **The backend's signed budget caps the run.** The signed request carries `{max_calls, max_tokens, max_cost_usd, model_tier_ceiling, deadline}` (`docs/entitlement-design.md` section 6). The executor takes the tighter of it and the definition's policy and never raises either.
- **Every tool call draws on one reservation** made before the run; the ledger settles it after, counting retries and failures.
- **Deadline and cancellation:** `AgentContext.deadline` and `is_cancelled()` are checked between steps; a cancel from the backend ends the run in `CANCELLED`.
- **Failure policy:** `max_consecutive_failures` (3) ends a run in `FAILED`; a tool failure reaches the agent as a structured failure with a fixed message (#57).
- **Terminal states** map to the student-visible outcome: `BUDGET_EXCEEDED` and `MAX_STEPS_EXCEEDED` return the best grounded partial result, marked partial, or `NOT_COVERED`; never a half-finished claim.

## 7. Online and offline, the same tools

| | Online | Offline (R2, Plus and Pro for local models; Free: the smallest model) |
|---|---|---|
| Tool schemas and names | The registry above | **The same JSON schemas**, shipped with the app |
| `search_course_material` | The hybrid retrieval engine over the durable index, with `denied_assets` | Hybrid retrieval over the active pack (`docs/offline-content-pack-contract.md`), under the lease |
| Generation | The Model Gateway (Gemini, and Fireworks if approved) | The local model portfolio, by entitlement |
| Loop | `AgentExecutor` | A device executor with the same ceilings. **Agentic workflows are Pro, R2**; an offline device runs the naive route unless the entitlement and the model allow more |
| `update_learning_progress` | Proposal to the backend | Queued, applied at sync, provisional until validated |
| Evidence and citations | `check_grounded`, citations from chunk metadata | The same rule, ported; citations from stored chunk metadata |
| Entitlements | Resolved per request | Carried in the lease |

Offline, a small model may follow only the naive route reliably. The offline planner is **not** assumed to match the online one, and the benchmark decides what a local model may run (plan phase 5). An offline run that can't ground an answer abstains.

## 8. Safety, audit and what the planner may never do

- **Never** read or write the database, call the network outside the gateway and the retrieval engine, or accept a tool name or permission from model output.
- **Never** set a score, mastery value, permission, entitlement or tenant.
- **Never** retrieve outside the student's scope or a denied document: `denied_assets` is required (`content.search` refuses without it).
- **Provenance:** every passage a run used is in `sources_used`; the backend runs its provenance check on the whole answer, and a revoked source withholds it all (`ANSWER_WITHHELD`).
- **Audit trail:** the `AgentEvent` stream (run, step, model call, tool call, terminal) is recorded with ids, counts, latencies and costs, **never** student text or passages. The log rule of #52 and #60 (exceptions by type and place only) applies.
- **Prompt injection:** retrieved passages and tool outputs are data. The planner's system prompt tells the model so, and a tool output can't change `allowed_tools`, the budget or the route. A test with an adversarial passage is required (section 9).
- **Exam mode:** no planner run starts during an official attempt (backend-enforced, the user's adopted decision).

## 9. Evaluation and acceptance

The planner doesn't ship until each class has passed an evaluation, on BUILD's own tasks, before any model role is assigned.

- **Task suite:** the plan's 100-task set (50 RAG, 30 orchestration, 20 question generation) plus agentic tasks for each agentic class: comparison, contradiction, multi-source research and revision plan.
- **Measures:** grounded-answer rate, citation accuracy, abstention (answers withheld when the material doesn't cover it), plan quality (a rubric), cost per task and latency, with confidence intervals.
- **Bars:** set before running (open decision), per class, and for each model that is a candidate.
- **Adversarial tests:** a passage that tells the agent to ignore its tools; a tool output claiming a new permission; a request to read another student's data; a proposal that tries to set a score. Each must fail safely.
- **Bound tests:** a run that would exceed each ceiling ends in the right terminal state; a cancel ends the run; a signed budget lower than the policy wins.
- **Tamper tests:** a Free or Plus user can't start an agentic run (`docs/entitlement-design.md` section 7).
- **Parity:** online and offline return the same tool-schema validation results for the same inputs.

## 10. Open decisions

1. Whether `search_course_material` replaces `content.search` or wraps it (proposed: wraps).
2. The planner's ceilings, from measurement.
3. Which model runs which stage: not assigned; benchmarks decide (the user's role hypotheses and the report's differ; plan section 14.5).
4. The evaluation bars per class.
5. The assessment-history inputs the backend will supply to `identify_knowledge_gaps`, and their contract (AI-10 and AI-11 depend on the same inputs).
6. The backend operation and contract for applying a progress proposal, and what "progress" excludes.
7. How a student approves a plan (a client flow and a contract).
8. What a student sees when a run is partial, declined for entitlement, or abstains.

## 11. Delivery (proposed order, none authorised)

1. This design approved; the open decisions settled or deferred.
2. Tool definitions and schemas, with validator tests (no route).
3. The routing rule table and its tests, naive only, in R1 form.
4. The backend contract for progress proposals and assessment-history inputs, paired in both repositories.
5. The planner `AgentDefinition` behind a disabled flag, with bound and adversarial tests.
6. The evaluation suite and a baseline before any bar.
7. Entitlement-gated exposure in R2, after the entitlement design ships.
8. The offline executor, after the content-pack contract and the device benchmark.
