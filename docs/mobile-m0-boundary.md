# Mobile boundary requirements (M0)

**Status: design approved by the reviewer on 2026-10-30.** Covers the M4 retrieval guarantee, the citation schema, and the M7 release gate. Conventions are in [mobile-api-conventions.md](mobile-api-conventions.md).

## M4: retrieval readiness

### The guarantee

> A retrieval result is eligible for a student-facing answer only when its associated ingestion job is in the `ready` state and the requesting user is authorized to access that document.

Today this doesn't hold. Retrieval filters by tenant only, so chunks are searchable from the moment they commit. An attempt that commits chunks and then fails leaves them searchable until the next attempt replaces them. The Phase 3 record accepted this as a limitation for this work to close.

The rule must cover **every path to retrieved text**, not just chat: `retriever.evidence` serves chat, explain and question generation, and `/v1/ai/retrieve` returns passages directly.

### Options

| | (a) Readiness index in AI metadata | (b) Backend-mediated filter |
|---|---|---|
| How it works | The backend tells the AI service when a document becomes eligible or stops being eligible; retrieval joins against that table | On each request, the backend sends the set of eligible documents in the signed call |
| Source of truth | Two copies that can drift | The backend alone |
| Revocation and failure | Delayed until the update arrives, so it needs an outbox and reconciliation | Takes effect on the next request |
| Per-user access | Must also replicate ownership and visibility | Already known to the backend |
| Performance | No extra lookup, and scales with chunks only | One backend query per request, and the payload grows with eligible documents |
| New failure mode | Silent drift, in the unsafe direction if a revocation is lost | Oversized payload, which fails visibly |

### Initial design: (b), confirmed by measurement in M4

The reviewer supports (b) as the initial design, provided M4 measures payload and recall at the scales below and missing eligibility information fails closed. Option (b) keeps authorization with its owner and fails safely, and the first release has few documents per student. Its cost is the payload, so M4 measures before committing:

- Latency and payload size at 100, 1,000 and 10,000 eligible documents.
- Search quality with the filter applied. A selective filter on an approximate vector index can return fewer results than asked for, so recall@5 must be compared with and without it, on the existing evaluation set.

If a limit is reached, M4 reports it and the choice returns to the reviewer. **M1 doesn't hardcode either option:** the public contract says nothing about how eligibility reaches the AI service.

### Shape of (b)

```text
allowed: [ { asset_id, run_number, attempt }, ... ]
```

- A document is eligible when it isn't revoked or superseded, the caller may read it, and its latest job is `ready`. The backend computes this in one query.
- Matching the `(run_number, attempt)` as well as the asset means chunks from any other attempt can't match, so a stale attempt can't be cited, even in a race.
- While a ready document is being reprocessed, it's unavailable from the moment its chunks are replaced until the new job is `ready`. This is deliberate: it's the safe side, and the UI shows the document as processing.
- An empty set means the AI service isn't asked to retrieve at all, and the answer is the fixed "not covered" reply.
- A missing `allowed` field is refused. Absence never means unfiltered.
- The AI service treats the field as authoritative only on a verified signed call.

M4 must check how this fits the signed-context format and body limits, and whether `chunk.attempt` is reliable enough for this. It's recorded today "for provenance".

### Required tests

| Document state | Expected |
|---|---|
| `queued` | Not retrievable |
| `processing` | Not retrievable |
| Chunks written, job not `ready` | Not retrievable |
| `failed`, with chunks left behind | Not retrievable |
| `ready` | Retrievable and citable |
| `ready` in another tenant | Not retrievable |
| `ready`, but the user has no permission | Not retrievable |
| Stale attempt replaced by a later attempt | Only the later attempt's chunks, and only once `ready` |
| Revoked after `ready` | Not retrievable on the next request |
| Becomes ineligible while an answer is being generated | Fails closed (below) |
| `allowed` missing from the signed call | Refused |

Each runs on every path to retrieved text, on real PostgreSQL.

## Citation schema

Returned by the backend, on `POST` of a chat message:

```json
{
  "answer": "...",
  "grounded": true,
  "citations": [
    {
      "number": 1,
      "source_id": "...",
      "asset_id": "...",
      "title": "...",
      "page_start": 12,
      "page_end": 13,
      "excerpt": "..."
    }
  ],
  "conversation_id": "...",
  "request_id": "..."
}
```

Field by field:

| Field | Comes from | Rule |
|---|---|---|
| `number` | AI service | Matches the `[n]` in the answer text |
| `asset_id` | AI service `document_id` | M4 confirms these are the same ID |
| `source_id`, `title` | Backend, looked up from the asset | Never produced by the model. `title` is the source's title or the file's display name |
| `page_start`, `page_end` | AI service | Nullable. Shown as absent, never guessed |
| `excerpt` | Text of the cited passage | Cited passages only, with a length limit set in M1 |
| `grounded` | AI service | `false` means the fixed "not covered" reply, and `citations` is empty |

Rules:

- **No invented metadata.** A value that can't be established is null, or the citation fails.
- **No internals:** no `chunk_id`, storage paths, or tenant IDs.
- **Uncited passages aren't returned.** Today's `context` field doesn't carry into the mobile contract.
- **Attribution is preserved from the AI service to the app, and the backend never blindly forwards model output.** It validates every citation's authorization after generation, because a document can stop being eligible while the answer is generated. If any citation fails, the backend doesn't drop it alone, since that would leave a dangling `[n]` in the text. It returns the fixed "not covered" reply with `grounded: false`, and logs the event without any content.
- Generated text stays visibly separate from source text in the UI (PRD §291).

## M7: release-blocking gate

`scripts/mobile_boundary_gate.sh` in this repository. It runs real services: backend, AI service, worker, PostgreSQL, Redis and object storage, with the test AI providers the boundary gate already uses. The client side uses the **generated mobile API client**, not hand-written requests, so the gate exercises what the app really sends.

### Test matrix

| # | Test | Setup and action | Must show |
|---|---|---|---|
| 1 | Valid session | Sign in, call a protected route | 200, with the expected user and tenant |
| 2 | Expired token | Use an expired access token | `AUTH_TOKEN_INVALID`; the client refreshes once and the retry succeeds |
| 3 | Revoked session | Sign out, then reuse both tokens. Also reuse a rotated refresh token | `AUTH_TOKEN_INVALID`, `AUTH_REFRESH_INVALID`; reuse revokes the session |
| 4 | Missing tenant header | Omit `X-Tenant-Slug` | `TENANT_REQUIRED` |
| 5 | User not in tenant | Send another tenant's slug, then an unknown slug | The same `TENANT_ACCESS_DENIED` for both |
| 6 | Cross-tenant document | Read, retrieve and cite another tenant's document by ID | `RESOURCE_NOT_FOUND`; nothing retrieved |
| 7 | Upload retry | Repeat with the same key and bytes; then the same key with different bytes | Original asset and one stored object; `IDEMPOTENCY_KEY_REUSED` |
| 8 | Worker failure and recovery | SIGKILL the worker mid-job | Lease expiry, `AI_TASK_LOST`, attempt 2, `ready`, as in C23 |
| 9 | Non-ready document | Ask about a document in each non-`ready` state | Never cited, and "not covered" if it's the only evidence |
| 10 | Ready document | Upload through to `ready`, then ask | A grounded answer citing that document |
| 11 | Citation integrity | Check every field of the citation in test 10 | Asset, source, title, pages and excerpt match the real chunk and asset; no internals |
| 12 | Citation authorization | Revoke access or the document, and race it during generation | Fails closed, with no citation to the revoked document |
| 13 | AI service unavailable | Stop the AI service, then ask | `AI_UNAVAILABLE`; no answer stored; recovers when it returns |
| 14 | Client contract drift | Run the drift checks below against a deliberately changed contract | The gate fails |

Tests 8, 12 and 13 control processes or timing, so they run as separate phases, like the existing gate's C23 and outage phases.

### Commit pinning

| Rule | Detail |
|---|---|
| Contract lock | The mobile repo commits `contract.lock.json`: the backend commit and the SHA-256 of the `openapi.yaml` its client was generated from |
| Mobile drift check | Mobile CI regenerates the client from that exact contract and fails on any difference |
| Backend drift check | The gate compares the served routes with `openapi.yaml`, and compares the lock's hash with the contract under test. A mismatch fails |
| Input | The gate takes three full commit SHAs. It refuses branch names on a release run |
| Pin updates | Default pins live in a committed file and change only by PR, so moving a pin runs the gate |
| Evidence | Each run writes `mobile-boundary-evidence.json`: all three SHAs, the contract hash, each test's result, and the run ID. Kept as a CI artifact and shown in the job summary |

**A release runs on the release candidate's own three SHAs, not on the default pins.** A green result on older pins says nothing about what is being shipped. The evidence file is what the release record cites.

### When it runs

- On every PR that changes this repository's mobile routes, on the pinned AI and mobile commits.
- By `workflow_dispatch` for a release, with explicit SHAs.
- Mobile and AI PRs run their own checks plus the drift check. The full gate needs a backend workflow run, as the existing boundary gate does.

The existing boundary gate is reused for topology and not weakened. Its 193-test main run continues separately.

### What M7 doesn't establish

A passing gate is not any of these, and the release record must say so:

- **Deployment readiness.** It doesn't verify SIGTERM, the stop timeout, SIGKILL or restart on a production host, and no production deployment is defined.
- **Retrieval or academic quality.** Test providers prove the plumbing, not that answers are good.
- **Behaviour on real devices.** The generated client runs in Node. Secure storage, app restarts during refresh, and native networking need device tests in M6.
- **Mobile UI behaviour.** Screens are covered by the mobile repository's own tests.
- **Load.** Single-user flows only.
- **Production providers**, such as the production database or a real model.
