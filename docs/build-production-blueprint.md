# BUILD Production Architecture & Operations Blueprint

**Status: proposed (2026-11-04).** This is the implementation reference for the production direction in the Master PRD's §0. It turns the agreed decisions into components, contracts and release gates. **Nothing here is implemented yet**, and each part goes through its own design approval before code, as every milestone does. Where this document and the PRD disagree, the PRD governs.

Unchanged by this document: the backend owns the public API, identity, tenancy, authorization and academic truth; the AI service owns intelligence and retrieval; the mobile app is a client of the backend only. Learning Memory stays disabled, and `GATE_OPEN` stays `False`.

## 1. Topology

```text
Android / iOS app (installed; not hosted)
        │  HTTPS
        ▼
build-backend (Cloud Run) ── Cloud SQL PostgreSQL ── Memorystore (Redis 8 class)
   │  identity · tenancy · entitlements · metering · update metadata · academic data
   │  signed calls (Service Signature v1)
   ▼
ai-service (Cloud Run) ── Model Gateway ── Gemini SDK (online)
   │  grounding: OCR · chunking · embeddings · retrieval · provenance · evidence checks
   ▼
Workers (Cloud Run jobs / worker pools): ingestion, OCR, indexing, outboxes

Cloud Storage: academic documents, images, APK releases (APKs behind a CDN)
Cloud Monitoring and Logging · Secret Manager · landing site (Firebase Hosting or Cloudflare Pages)
```

**To verify before committing to it:**

| Check | Must hold |
|---|---|
| Cloud SQL | PostgreSQL 17 with pgvector 0.8, as the AI index uses today |
| Managed Redis | Meets the Redis 8 requirement. If it doesn't, the requirement isn't weakened; another hosting option is chosen |
| Region | Latency from Nigeria and cost, measured for `africa-south1`, `europe-west1` and `europe-west4`. The API and the database share a region |
| Roles | The least-privilege database roles (owner, runtime) from the boundary topology carry over unchanged |

## 2. Online intelligence: the Gemini adapter

- **Where it lives:** a provider adapter behind the AI service's existing Model Gateway. Nothing outside the gateway imports the SDK.
- **Configuration:**
  - `MODEL_PROVIDER=gemini`, with the model name from configuration.
  - Free models in development and test; the deterministic provider stays for tests and is refused in staging and production, as today.
- **Before it's built on:** the production target, Gemini 3.8 Flash, is verified. That means its exact model identifier, its availability in the chosen region, its pricing and data terms, and whether it supports structured output and the multimodal input BUILD needs.
- **Data governance:** G-33 still applies. **No production provider receives student or institutional passages** until BUILD has recorded the provider's training use, retention, processing terms, subprocessors and locations, and deletion. The required default is that the provider may not train on BUILD's content.
- **What the gateway owns:**
  - timeouts, retries and circuit breaking
  - per-request token budgets from the backend's entitlement
  - fallback
  - cost and latency metrics
  - structured-output validation

## 3. Grounded academic intelligence

The layer that decides what an answer may claim. Most of it exists today:
- **Scope and denial:** the knowledge scope, the denial list and the signed provenance envelope (M3-D).
- **Retrieval:** hybrid retrieval over pgvector and keyword search.
- **Evidence:** citation checks, and `NOT_COVERED` abstention.

**Still to build:**

| Gap | Where |
|---|---|
| The read-policy provenance check, returning `ANSWER_WITHHELD` | M3-D PR 4 |
| Real-document retrieval quality: 62.5% recall@5 on real FUTA material against 94.6% on the controlled set | A P3-5 follow-up. Its gate measures the real set, not the controlled one |
| OCR coverage of scanned pages (1,459 not yet OCRed) | The ingestion and OCR lane. Gemini-assisted extraction is routed by document type, validated, and keeps page provenance |
| Gemini's extracted text treated as text to ground, never as an answer | Gateway and ingestion |

## 4. RAG routing

A routing policy in the AI service's orchestration, as configuration:

| Signal | Route |
|---|---|
| A single well-scoped request: define, summarize, explain from material, generate questions from a chapter | Naive RAG |
| Multi-source, comparative, contradiction-finding or planning tasks | Agentic RAG |
| No entitlement for agentic depth | Naive RAG, with an honest note that deeper analysis is a higher-allowance capability. **Never an ungrounded answer** |

- **Agentic runs** use the existing agent runtime's bounds: permissions, step and tool budgets, deadlines and cancellation, plus an iteration limit on retrieval. Every retrieval step goes through the same scope, denial and provenance rules.
- **Evaluation:** each route is measured for cost, latency and answer quality. Agentic RAG is used only where it measurably helps.

## 5. Offline intelligence

**First benchmark portfolio:**

| Role | Candidates |
|---|---|
| General model | Qwen3-1.7B first, Qwen3-0.6B as the low-memory fallback, Glimmer 2B if its licence and weights allow. Gemma 3 1B and SmolLM2-1.7B as comparisons |
| Retrieval | A small embedding model, and an optional reranker |
| OCR | A PaddleOCR / OpenVINO-class model |

**Benchmark on real Android devices across low, mid and high RAM:**
- quality on BUILD's own tasks: explanation, question answering over local material, CBT support
- tokens per second, time to first token and memory
- battery and thermal behaviour
- model size, and the download cost on student data plans

**Selection** follows PRD §146.16. The runtime and its packaging (for example llama.cpp, MLC or ExecuTorch) are chosen by the same benchmark.

**Offline guarantees** carry over from the approved M3-D design:
- the authorization lease, measured in monotonic time, failing closed
- provisional offline answers that are validated on reconnect
- revocation reaches the device at each sync

## 6. Subscriptions and entitlements

**Levels:** Free, Plus, Pro and Campus (PRD §81). Prices come after cost measurement.

**Proposed backend schema,** designed and reviewed in its own design PR before migration:

| Table | Holds |
|---|---|
| `plans` | Plan code, entitlements and limits as data, so they can change without code |
| `subscriptions` | User, plan, source (`play`, `direct`, `campus`, `promotion`), status, current period, verified purchase reference |
| `purchase_verifications` | Append-only: provider, token hash (never the raw token in logs), the provider's response summary, the result, the time |
| `entitlement_grants` | Campus and promotional grants: who granted them, scope, period, reason. Audited |
| `usage_ledger` | Append-only metering: user, tenant, feature, model, units, cost estimate, request ID |
| `entitlement_overrides` | Administrative overrides, each audited with actor and reason |

**Enforcement:**
1. The backend resolves the entitlement on every protected request.
2. The AI service receives a budget only inside the signed call's context or body, and never trusts a client-supplied plan.
3. Metering is charged in the same transaction as the work it charges for, where possible.
4. A modified APK can change what the app shows, never what the backend grants.

**Purchases:** a provider-independent verification port. The Google Play Developer API adapter is used on Play. A server-verified adapter covers direct APK payments. Renewals, cancellations, refunds and expiry update state through provider notifications and periodic reconciliation.

## 7. App versions and updates

**Proposed contract:** `GET /app/updates?platform=android&version_code=N`, authenticated or not, with no personal data:

```json
{
  "platform": "android",
  "latest_version": "1.1.0",
  "latest_version_code": 3,
  "minimum_supported_version_code": 2,
  "mandatory": false,
  "release_notes": ["..."],
  "download_url": "https://<cdn>/build/1.1.0.apk",
  "sha256": "<release file sha256>"
}
```

- `mandatory` is computed against the caller's `version_code`. The same contract later returns the Play listing as `download_url`.
- **The release record** lives in the backend: version, notes, minimum, destination, file hash, and who published it, audited.
- **The client** checks after login, shows each optional release once, and blocks below the minimum.
- **Signing key custody:** one owner, an offline backup, and a documented recovery. It's never in CI logs or the repository. Losing it breaks in-place updates.
- **EAS Update** delivers compatible JS and asset changes, with runtime versions pinned. A native change always means a new APK and a new `versionCode`.

## 8. The Platform Operations Layer

These are owned by the backend, never the client, and each is audited:
- entitlement and usage administration
- AI cost accounting per model and feature
- app release and minimum-version management
- feature flags
- model configuration and routing policy
- service health and deployment status
- release history and rollback

## 9. Release gates

A release candidate needs every one of these, each with evidence:

| Gate | Evidence |
|---|---|
| The M3 security and contract gates | Merged, with the drift gate and boundary gate green on pinned SHAs |
| The student journey (PRD §0.1) | Exercised end to end against the real stack with the generated client, with no stubs (M7) |
| AI acceptance (PRD §0.6) | Each of the eight items demonstrated, including real-document retrieval quality and genuine on-device generation |
| Entitlements | A tampered client can't raise its entitlement: tested against the API |
| Updates | An in-place update from the previous signed APK keeps the student's data. A version below the minimum is blocked |
| Provider governance | G-33 recorded before any production provider receives content |
| Operations | Cost, latency, error rate and provider availability visible, with alerts. Backups and restore tested. TLS in front of every service |
| Learning Memory | Still disabled, with `GATE_OPEN` `False`, unless its own gate has been passed |

## 10. Open verifications

1. The exact Gemini production model identifier, availability, pricing and data terms.
2. Cloud SQL's support for PostgreSQL 17 with pgvector, and managed Redis 8.
3. Region latency from Nigeria.
4. Glimmer 2B's licence and weights.
5. The direct-APK payment provider.
6. Google Play billing policy at the point of Play distribution.
7. Signing-key custody.
8. The Apple Developer account, for iOS.
