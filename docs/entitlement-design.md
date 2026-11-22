# Entitlement design (DRAFT)

**Status: draft design for the reviewer. It authorises no migration, route, quota, provider or deployment.** The capability policy it implements is provisional (`docs/BUILD_IMPLEMENTATION_PLAN.md` section 14.2). Exact quotas, model assignments, cost limits and Campus rules are left unspecified until separately reviewed.

**Follows:** `docs/build-production-blueprint.md` section 6 (the schema sketch), PRD §78 to §88 and §84.1.

## 1. What exists today (checked 2026-11-20, `origin/main` `e9067ed`)

- **No backend entitlement, subscription or plan code.** `git grep` for "subscription" and "entitlement" in `app/` and `alembic/` finds nothing.
- **No usage metering.** `app/api/ai.py` resolves a tenant context and an actor with a permission (`_actor`, line 95) and calls the AI assistant gateway; nothing counts what a call costs.
- **The AI service budgets per request from its own settings** (`AI_BUDGET_{CHAT,EXPLAIN,QUESTIONS,CBT}_{CALLS,TOKENS,COST_USD}`, `ai-service/README.md`), reserved before each call and reconciled after (`ai-service` `docs/ai-01-model-gateway-design.md`). It accepts no budget from the backend yet.
- Alembic head `0032`; the next free revision is held by the M3-D lane (`0033`). This design's migration asks the head's owner for its number.

## 2. Principles

1. **The backend is the only authority** (PRD §84.1). A modified APK that shows "Pro" still gets what the backend says.
2. **Two separate entitlements:** *model tier* (which models a request may use) and *agentic capability* (which agentic workflows a student may start). Neither implies the other, and a plan name never grants a costlier model.
3. **Budgets are server-authoritative.** They count provider cost, retries and failed requests.
4. **Entitlements gate capability, never authority.** No entitlement gives a say over assessment scores, mastery, permissions or tenant isolation.
5. **Free is enforced in the backend**, not by hiding buttons.
6. **Plans are data**, so limits change without a release.

## 3. The policy this implements (provisional, updated 2026-11-20)

| Plan | Online | Offline (R2) | Agentic (R2) |
|---|---|---|---|
| Free | A very low-cost model for ordinary questions, under strict backend budgets (low-cost, not zero-cost). Target: a Fireworks model once approved; R1: Gemini under a strict budget | The smallest local model | None |
| Plus | Free's online access plus the approved online capabilities, subject to budget | The full benchmark-selected local portfolio | None |
| Pro | Everything in Plus | Everything in Plus | Full bounded agentic study workflows: multi-step research and synthesis, personalised study planning, reading paths; routed across Gemini and the three Fireworks models by capability, quality, cost, latency and availability |
| Campus | Institution-sponsored access; **undefined** | | |

Offline **reading** of downloaded materials is free for everyone; only AI inference is entitled. In R1: online-first, Gemini a **designated first R1 provider candidate, currently not approved or enabled** (provider work is paused, user decision 2026-11-21), no offline AI, no agentic workflows, and Plus and Pro only as **granted** states (payments are paused, PRD §0.5). Gates before defaults: the Free online model must clear a minimum grounded-answer, citation and abstention bar in evaluation, and the smallest local model a minimum abstention bar, before either ships to Free.

**Subscription wording (user, 2026-11-20; this wording governs where the tables differ):**
- **Free** = strictly budgeted online AI; the smallest local model in Release 2, after it passes evaluation.
- **Plus** = the full local model portfolio in Release 2.
- **Pro** = Plus entitlements and bounded agentic workflows using approved Gemini and Fireworks models.
- **Campus** = undefined, pending a separate entitlement decision.
- Offline reading remains free for everyone when it ships.

**No paid Fireworks call is authorised.** There is no Fireworks key and the wallet is unfunded (user, 2026-11-20). The reviewer recommends $0 evaluation until governance and evaluation controls are ready, then a separate, explicit spending decision by the user. Before any paid call, all of these must hold:
1. The governance documentation (the G-33 record) is reviewed.
2. Model IDs are verified and current pricing is confirmed.
3. A written evaluation plan exists, using **synthetic passages only** (the offline-bench lane is writing it in `ai-service`).
4. A hard spend limit, with request and token limits and an automatic stop, is in place.
5. Results and costs are recorded.
6. The user has approved the cap in writing.

### 3.1 An entitlement is not provider approval

**Gemini cannot receive student material until its G-33 approval and paid-tier prerequisites are met.** Provider work is paused by the user pending the age-eligibility question (2026-11-21). The backend must therefore **not treat the designated R1 provider as operationally approved**.

- Entitlement resolves a *right*. Whether a provider may be called at all is a separate, operational fact reported by the gateway (`MODEL_PROVIDERS_APPROVED`, empty by default).
- A request that needs a model needs **both**: an entitlement and an approved provider. If either is missing it fails closed with a stable code, and no budget is reserved.
- "Free online" in the table above is therefore a design target, not a promise that student passages can be sent anywhere today.

## 4. Data model (proposed)

Extends the blueprint's sketch. Names are proposals.

| Table | Holds | Notes |
|---|---|---|
| `plans` | `code` (`free`, `plus`, `pro`, `campus`), `version`, `status` | Versioned rows; a subscription points at a version |
| `plan_entitlements` | plan version, `capability` key, `limits` (JSON checked against a schema per capability) | One row per capability. Capability keys: `ai_tutor`, `model_tier`, `offline_ai` (`none`, `smallest`, `portfolio`), `agentic_workflows`, `multi_hop`, `reading_paths` |
| `subscriptions` | user, plan version, `source` (`promotion`, `campus`, `admin`; later `play`, `direct`), `status`, period | R1: only the granted sources |
| `entitlement_grants` | user or tenant, plan or capability, scope, period, granter, reason | Audited. Campus and promotional grants |
| `entitlement_overrides` | user, capability, value, actor, reason, expiry | Audited; never silently permanent |
| `usage_ledger` | append-only: user, tenant, feature, provider, model, units, cost, outcome (`ok`, `retry`, `failed`), request id | Written for failures and retries too |
| `usage_reservations` | request id, reserved amount, state (`reserved`, `settled`, `released`), expiry | Reserve before the AI call, settle after |
| `purchase_verifications` | as the blueprint sketch | **Created empty or deferred**: R1 has no purchase flow |

All tenant-scoped tables carry the tenant key, following the composite tenant-key rule of the S-02 design (`docs/s-02-academic-profile-design.md`), if the reviewer keeps it.

### 4.1 Grant authority (policy only; PROVISIONAL and OPEN; nothing implemented)

> **Not an approved authorisation model.** Everything in this section is a proposal: who may grant and revoke, whether a campus administrator may grant Plus and Pro, the maximum grant duration, second-operator approval for entitlement-raising overrides, the platform-operator role boundaries, and every Campus rule. Each is **provisional and open** for the reviewer and the user. Nothing here authorises a role, a permission or an operator capability.

| Action | Who may do it | Rules |
|---|---|---|
| Grant Plus or Pro (promotional or admin) | A platform operator with the grant permission | A reason is required; an **expiry is required** (the maximum period is an open decision); no open-ended grants |
| Grant Plus or Pro on behalf of an institution | **Open.** Proposal: a tenant administrator grants **nothing** until Campus is defined, because Campus allocation is undefined | Whether a campus administrator may grant both Plus and Pro is a decision for the Campus design |
| Revoke a grant | The granter, or a platform operator | Effective at the next resolution; recorded with a reason |
| Override a capability (raise, lower or deny) | A platform operator; proposal: a second operator's approval to *raise* | A reason and an **expiry are required**; no permanent override |
| A student granting or raising their own plan | Nobody | Refused |
| Granting above one's own authority | Nobody | A grantor can't confer more than their role allows |

**Audit:** every grant, revocation and override writes an append-only row: actor, actor's role, subject user, capability or plan, value, reason, period, request id and time. It holds ids and codes, never student text. The log is read by operators with a separate permission.

### 4.2 Ledger accounting

The usage ledger (`usage_ledger`, `usage_reservations`) is append-only and records, per model call:

| Field | Meaning |
|---|---|
| `cost_estimated` | The cost computed before and at the call from the pricing table |
| `cost_provider_reported` | The cost the provider reports, when it does; null until then. A report arrives as an **adjustment row**, never an edit |
| `pricing_version` | The price table version used, so a later price change doesn't rewrite history |
| `input_tokens_uncached`, `input_tokens_cached`, `output_tokens` | Cached and uncached input are priced differently and are recorded separately |
| `provider`, `model` | Per-model usage, so budgets and reports can be read per model |
| `request_id`, `original_request_id`, `attempt` | A retry carries its original request's id and an attempt number, so retries are visible and counted |
| `settlement_key` | Unique on (`request_id`, `attempt`). A second settlement with the same key is **rejected**, which prevents duplicate settlement |
| `outcome` | `ok`, `retry`, `failed`, `cancelled` |

Budgets count settled cost; until the provider reports, the estimate counts, and a failed or cancelled call counts its estimate until reconciled. The AI service's usage in the signed response is the source for settlement; a missing report settles at the estimate and is flagged.

## 5. Resolution

For each protected request the backend resolves `effective(user, capability)`:

1. Start from the user's active subscription's plan version (Free if none).
2. Add active grants (a grant can raise, never exceed the plan family it names).
3. Apply overrides.
4. A revoked, expired or refunded source removes its contribution at once.
5. The result is a capability value, e.g. `model_tier = small`, `agentic_workflows = none`, with its limits.

Rules: **model tier and agentic capability resolve independently.** Free resolves `offline_ai = smallest`, Plus `portfolio`, and neither resolves `agentic_workflows` above `none`. Resolution is a pure function over rows, so it can be tested with no AI service.

### 5.1 Precedence (deterministic, for the R1 Free, Plus and Pro cases)

`effective(user, capability)` is a pure function of rows and the database clock at request time. **Campus and tenant sponsorship are deferred: they contribute nothing in R1.**

1. Each capability has an ordered value domain, for example `offline_ai`: none < smallest < portfolio; `agentic_workflows`: none < full; `model_tier`: none < small < medium. Capabilities resolve **independently**.
2. Start from the Free baseline.
3. Take the **maximum** of the baseline, the active subscription's plan value, and every **active** grant's value. A source is active when the current database time is within its period and it isn't revoked. An expired or revoked source is ignored.
4. Apply overrides last. An override **replaces** the value for that capability, whether it raises or lowers it. At most one override is active per user and capability; if rows conflict, the most recently created wins, ties broken by row id.
5. A **deny** override (a suspension) beats every grant and plan.
6. Tenant sponsorship rows, if any exist, are **ignored in R1** and reserved for the Campus design.
7. A plan name never grants anything: only `plan_entitlements` rows count.
8. Provider approval is separate (section 3.1) and applied after resolution.

| Case | Result |
|---|---|
| A Free user with an active promotional Plus grant | `offline_ai = portfolio`, `agentic_workflows = none` |
| A Pro subscriber with a deny override on agentic workflows | `agentic_workflows = none`, other Pro values stand |
| A Plus grant that expired yesterday | Ignored: the user resolves as Free |
| A grant and an override in conflict on `model_tier` | The override wins |
| A tenant sponsorship row on a Free user | Ignored in R1 |

## 6. Enforcement

1. **On every protected request** the backend resolves the entitlement. A denied capability returns a stable error code in the shared error shape.
2. **Before an AI call** it reserves budget: `usage_reservations` row inside the transaction that records the request. If the reservation would exceed the period limit, no call is made.
3. **Signed budget in the AI call** (a proposal, **not authorised by this design**: it is a shared backend and ai-service contract change that needs its own paired PR and the reviewer's approval first). The signed request body carries `{budget: {max_calls, max_tokens, max_cost_usd, model_tier_ceiling, deadline}}`. The AI service enforces the tighter of this and its own `AI_BUDGET_*` and never raises either. It never reads a plan name, and never trusts a client-supplied value. *This is a contract change in both repositories and needs its own paired PR.*
4. **Settle after the call** from the signed response's usage, counting retries and failures. Unsettled reservations expire and are swept.
5. **Free restrictions live here**, in resolution and reservation, not in the UI.
6. **Offline AI** is entitled by the signed **model-pack download** and a periodic entitlement lease (R2; see the content-pack contract). That is distribution gating. The backend can't stop a modified APK from running side-loaded open-weight models, and this design doesn't claim it can.
7. **Agentic workflows** (R2) are started only if `agentic_workflows` resolves; every tool call in a workflow draws on the same reservation (see the study-planner design).

## 7. Tamper tests (required before any route ships)

| Attack | Expected |
|---|---|
| A modified client sends `plan: pro` or `model: large` | Ignored; Free behaviour |
| A Free user calls an agentic or multi-hop route directly | Denied by the backend with a stable code |
| A Plus user starts an agentic workflow | Denied: Plus offline AI doesn't grant Pro agentic |
| A revoked grant is replayed from a cached token | Next request resolves without it |
| Retries or failed calls | Counted in the ledger and against the budget |
| Two concurrent requests at the limit | At most one reserves; a race test on PostgreSQL |
| The AI service receives a larger budget than the backend signed | Cannot: the budget is inside the signature |
| An entitlement lease expires on a device | The model pack's use is refused at its next lease check (R2) |
| Cross-tenant grant or ledger read | Denied |
| Plan name alone for a costlier model | Never grants it |

## 8. What is provisional, and what is open

**Provisional (not to be hardcoded):** the capability table, all limits, which models belong to which tier, the budgets, and period lengths.

**Open decisions:**
1. *Decided 2026-11-20:* Free gets the smallest local model; offline *reading* is not paywalled (PRD §78 to §80). Open: the abstention bar it must clear.
2. Cost. A typical tutor answer (8,000 input, 500 output tokens) is about $0.016 on Gemini at the 2027 price against about $0.0005 on the small Fireworks tier at uncached prices (page's unverified prices), roughly 30 to 80 times with caching. This is an **unverified planning estimate**, not a recommendation to act. Provider governance and evaluation remain paused under the user's 2026-11-21 decision, and nothing here authorises resuming them.
3. Budget periods (daily, monthly) and what a student sees when a limit is reached.
4. Who may grant Plus and Pro in R1, and how grants are audited.

### Campus: left undefined

Campus is a separate, institution-managed policy. It is **not** inferred from the student plans. Questions it needs answered before design:
- Who holds the entitlement: the tenant, a cohort, or each student?
- Who pays, and who decides the allocation per student or per course?
- Are per-student limits fixed by the institution or pooled?
- May an institution see its students' usage? At what granularity, given privacy?
- What happens when the institution lapses: do students fall to Free or to a grace period?
- Does Campus unlock any capability beyond Pro, or only allocation?
- How do grants interact with a student's own purchased plan?

## 9. Delivery (proposed order, none authorised)

1. This design approved.
2. Migration and the pure resolution function with unit tests (no routes).
3. Usage ledger and reservations, with the PostgreSQL race tests.
4. *Not authorised by this design:* the signed-budget contract change, which would need its own paired `ai-service` and build-backend PR, the boundary gate and separate approval.
5. Enforcement on the existing AI routes (`app/api/ai.py`) for Free.
6. Grants and overrides (admin) with audit.
7. Tamper tests green, then the contract PR for any client-visible operation.

## 10. Decisions the reviewer must make

1. Approve the data model and the two-entitlement split.
2. Decide whether to propose the signed-budget field as a shared contract; that would be its own paired PR in both repositories.
3. Choose how R1 grants Plus and Pro, and who may.
4. Set the evaluation bars (grounded answers, citations, abstention) for the Free online default and the smallest local model.
5. Start the Campus questions.
