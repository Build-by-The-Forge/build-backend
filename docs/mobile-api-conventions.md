# Mobile API conventions (M0)

**Status: design approved by the reviewer on 2026-10-30. M1 starts after this document merges.**

These are the rules the mobile contract (`contracts/mobile/openapi.yaml`, M1) must follow, and the decisions that must be settled first. They describe the intended API. Where today's backend differs, the difference is listed in the [inventory](mobile-m0-inventory.md) and closed in M3. Accepting these rules doesn't mean any endpoint already complies.

Companion documents:

- [Capability and gap inventory](mobile-m0-inventory.md): what exists today, and what's missing.
- [Boundary requirements](mobile-m0-boundary.md): M4 retrieval readiness, the citation schema, and the M7 release gate.

The product specification is the [master PRD](https://github.com/Build-by-The-Forge/Build-UI./blob/main/mobile-app-main/docs/BUILD_FRONTEND_MASTER_PRD.md) in the mobile repository.

## Decisions

The reviewer approved all four as proposed, with the conditions recorded in each section below. This is the reviewer's design ruling, not a formal GitHub approval.

| # | Decision | Ruling |
|---|---|---|
| A | Who owns conversations | The backend: server-issued IDs and persisted history. Retention is still open |
| B | Who can see an uploaded document | The uploading student only, in the first release. If that can't be made safe, no student uploads |
| C | How students get into a tenant | The existing join and invitation routes are in the first release |
| D | Upload read timeout | Raise it, to a value measured and documented in M3-D |

Details are under [Decision A](#decision-a-conversation-ownership), [Decision B](#decision-b-uploaded-document-visibility), [Decision C](#decision-c-tenant-entry) and [Decision D](#decision-d-upload-read-timeout).

## Ownership

- The backend owns the public API, identity, tenancy, authorization and academic truth.
- The AI service owns intelligence and retrieval. Mobile never calls it; only signed backend calls reach it.
- The mobile app is a client of the backend. The UI is never an authorization boundary (PRD §223).
- A contract change names its effect on the mobile app (PRD §285).

## First-release scope

The first release is **student only**, with no lecturer or admin mutations. The inventory lists every route. Not in the first release:

- `/ai/explain`, `/ai/memory`, `/ai/generate-questions`, and streaming chat (PRD §107)
- Reading Mode, Knowledge Trees, analytics, practice-question generation
- Offline exams and offline AI, which need their own decisions (PRD §183)
- Campus maps as a backend feature; the app's bundled map is unaffected

## Authentication

| Rule | Value |
|---|---|
| Access token | `Authorization: Bearer`, valid for 15 minutes (`expires_in` is authoritative) |
| Refresh token | Sent in the JSON body of `POST /identity/refresh`; rotated on every use |
| Refresh idle limit | 14 days |
| Session absolute limit | 30 days |
| Sign-out | `/identity/logout` revokes this session; `/identity/logout-all` revokes every session |
| Storage on the device | Secure storage only (PRD §61). Never in logs, URLs or analytics (PRD §222) |

All lifetimes are configuration. The contract documents the defaults, and clients must use `expires_in` rather than assume them.

**Refresh is single-flight on the client.** The backend treats a second use of a rotated token as theft and revokes the whole session, and that stays strict. So the client must:

1. Allow one refresh at a time, per session, including across app restarts.
2. Save the new refresh token before it uses the new access token.
3. Sign the user out on `AUTH_REFRESH_INVALID`, and never retry that token.

**Accepted cost:** if a refresh response is lost in transit, the client still holds the rotated token, so its retry revokes the session and the student signs in again. This fails safe, and flaky mobile networks will make it more common than it is on web. The reviewer kept the strict policy for now and accepted this cost. Device tests in M6 must exercise it. M7 measures nothing about its frequency. If it proves disruptive, changing the rule is a separate security decision.

## Tenant context

- The client sends `X-Tenant-Slug` on every tenant-scoped request.
- It is context, not proof. The backend resolves it and checks an active membership on every request.
- A missing header is `TENANT_REQUIRED`. An unknown tenant and a tenant the user doesn't belong to give the same `TENANT_ACCESS_DENIED`, so tenant existence isn't disclosed.
- A resource in another tenant is `RESOURCE_NOT_FOUND`, the same as one that doesn't exist.
- Request bodies can't name a tenant or a user.
- When the active tenant or user changes, the client clears or isolates cached data (PRD §224, §225). This doesn't replace the backend's checks.

## Envelopes

These apply **only to routes in the mobile contract**. Internal and admin routes change later or not at all, and the signed AI callback keeps its own contract.

Success:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": { "request_id": "..." }
}
```

Failure:

```json
{
  "success": false,
  "data": null,
  "error": { "code": "RESOURCE_NOT_FOUND", "message": "...", "details": null },
  "meta": { "request_id": "..." }
}
```

- `request_id` moves into `meta`. The `X-Request-ID` response header stays.
- `error.code` is stable and is what clients branch on. `error.message` is safe to show but may change.
- Responses never contain stack traces, internal addresses, storage URIs, or the text of an unexpected exception (PRD §232).

## Error codes

The registry below is the starting set. M1 fixes the full list, and M3-A implements it. A code is never reused with a new meaning.

| HTTP | Code | Client action |
|---|---|---|
| 400 | `TENANT_REQUIRED` | Choose a tenant |
| 401 | `AUTH_INVALID_CREDENTIALS` | Show a sign-in error, which doesn't reveal whether the account exists |
| 401 | `AUTH_TOKEN_INVALID` | Refresh once, then retry the request once |
| 401 | `AUTH_REFRESH_INVALID` | Sign out. Expired, revoked and reused tokens look the same |
| 403 | `ACCOUNT_NOT_ACTIVE` | Explain; no retry |
| 403 | `EMAIL_VERIFICATION_REQUIRED` | Go to email verification |
| 403 | `TENANT_ACCESS_DENIED` | Return to tenant selection |
| 403 | `PERMISSION_DENIED` | Explain; no retry |
| 404 | `RESOURCE_NOT_FOUND` | Show not found. Also used for other tenants' and other users' private resources |
| 408 | `UPLOAD_READ_TIMEOUT` | Retry with the same `Idempotency-Key` |
| 409 | `CONFLICT` and specific codes such as `IDEMPOTENCY_KEY_REUSED`, `DUPLICATE_CONTENT`, `ATTEMPT_ALREADY_SUBMITTED` | Reconcile with server state |
| 413 | `UPLOAD_TOO_LARGE` | Explain the limit |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Explain the accepted types |
| 422 | `VALIDATION_FAILED` | Show field errors |
| 429 | `RATE_LIMITED` | Wait for `Retry-After`. The message doesn't reveal which limit fired |
| 500 | `INTERNAL_ERROR` | Offer a retry only if the operation is safe to repeat |
| 502 | `AI_UPSTREAM_ERROR` | Offer a retry |
| 503 | `AI_UNAVAILABLE`, `OBJECT_STORAGE_UNAVAILABLE` | Wait for `Retry-After` if present, then retry |

Validation errors use one shape, and never echo the submitted value:

```json
"details": { "fields": [ { "field": "body.email", "code": "invalid_format", "message": "..." } ] }
```

## Pagination

- List routes take `limit` (default 50, **maximum 100**) and `offset` (default 0). Out-of-range values are `VALIDATION_FAILED`.
- The response adds `meta.pagination: { "total", "limit", "offset" }`.
- Every list has a deterministic order that ends in a unique tie-breaker, normally `id`.
- No cursors in the first release.

A bounded list that is small by nature, such as the caller's memberships, may be documented as unpaginated. Each exception is named in the contract.

## Idempotency

| Operation | Rule |
|---|---|
| Upload | `Idempotency-Key` required. Same key and bytes return the original asset with 200. Same key with different bytes is `IDEMPOTENCY_KEY_REUSED` |
| Create ingestion job | A repeat for an asset with an active job returns that job. To be implemented if M2 confirms it's missing |
| Start attempt | Returns the active attempt if there is one (already true) |
| Save or delete answer | `PUT` and `DELETE` on one question, so a repeat leaves one answer |
| Submit attempt | A repeat returns the submitted attempt or a defined conflict, and never grades twice. M2 verifies which applies today |
| Send chat message | `Idempotency-Key` required, so a retry can't create a second turn (Decision A) |
| Register | A repeat doesn't create a second account and doesn't reveal whether the account exists |

The client retries only what this table marks safe, with bounded attempts and respect for `Retry-After` (PRD §243).

## Versioning

- The contract carries a semantic version in `info.version`.
- Paths stay unprefixed for the first release, because moving 115 routes gains nothing yet.
- Within a version, changes are additive: new routes, new optional request fields, new response fields. Clients must ignore response fields they don't know.
- A breaking change gets a new `/v2/...` path for the affected routes. The old route stays until the oldest supported app version no longer needs it, because installed apps can't be updated at once.
- CI compares the contract with its last released version once M2 exists.

## Identifiers, time and tracing

- IDs are opaque strings. Clients don't parse them or assume a format.
- Timestamps are UTC, RFC 3339.
- The client may send `X-Request-ID`. The backend accepts it only if it matches `[A-Za-z0-9._:-]{1,128}`, otherwise it generates one. Every response returns the value, and the same ID reaches the AI service as the correlation ID.

## Uploads

| Rule | Value |
|---|---|
| Transport | Raw request body to `POST /content/sources/{source_id}/assets/upload`, with `file_name` as a query parameter for display only |
| Size limit | 25 MiB by default (`max_upload_bytes`), enforced while reading |
| Types | PDF, PNG and JPEG, decided from the bytes. The `Content-Type` header decides nothing. DOCX and PPTX appear in an enum but aren't accepted |
| Checksum | The server computes SHA-256 and returns it. The client compares it with its own to confirm the bytes arrived |
| Idempotency | Required, as above |
| Failures | Typed codes, as above |
| Resumable upload | Not in the first release |

The response never includes `storage_uri`.

### Upload states

The UI shows only what the backend reports (PRD §92–§96, §294, §295):

| UI state | Source |
|---|---|
| Uploading | Client only, until the upload response |
| Uploaded | The asset exists; no job yet, or job status `uploaded` |
| Queued | `queued` |
| Processing | `processing`, `extracted`, `chunked`, `indexed` |
| Ready | `ready`, and only then. A later-stage status such as `indexed` doesn't count |
| Failed | `failed` and not retryable |
| Retry available | `failed` and retryable, and a student action exists for it (see gap G-12) |

Polling is bounded and backs off (PRD §96). No percentage is shown, since the backend doesn't report one.

## Decision A: conversation ownership

**Approved: backend-owned conversations.** The backend issues the IDs and owns persistence, authorization, retention and deletion.

Today nothing is persisted: `app/api/ai.py` says so, and neither repository has a conversation table. The AI service takes one `message`, with no history. PRD §113 requires persistence "through the approved API", so stateless-only would conflict with the PRD.

| | Backend-owned | Stateless per message |
|---|---|---|
| History across devices | Yes | No |
| Tenant and user ownership | Enforced by the backend, like other resources | Not applicable |
| Student data held | Yes, so retention and deletion are needed | None |
| Cost | Tables and routes in M3-F | Nothing now, but a later migration |

Requirements:

- The backend issues `conversation_id`. It belongs to one user in one tenant; anyone else gets `RESOURCE_NOT_FOUND`.
- A turn is stored only after the AI step succeeds, together with its citations. A failed call stores no answer.
- A student can delete their own conversation. Conversation text never goes to analytics (PRD §231).
- **Accepted limit:** each turn is still answered on its own at first, because the AI service takes no history. So history is for reading and returning to, and follow-up questions won't understand earlier turns. Passing bounded history to the AI service is a separate AI contract change, not assumed here.
- **Open product decision:** how long conversations are retained. It must be settled before conversations are released to students.

M0 needs no migration. M3-F will.

## Decision B: uploaded document visibility

**Approved: private to the uploading student in the first release.** Shared tenant material stays staff-uploaded and read-only for students.

Reasons: student files may be personal or copyrighted, sharing needs moderation that doesn't exist, and a leak between students is much harder to undo than adding sharing later. ADR `docs/decisions/001-source-of-truth.md` already says student content doesn't define curriculum.

Either choice needs work, because **today's backend supports neither for students**:

| Layer | Today | Needed for private |
|---|---|---|
| Permission | Students lack `content.asset.upload` and `content.job.manage` | Own-document upload and ingestion permissions, without widening staff ones |
| Source | Upload needs a source, and students can't create one | A personal source per student per tenant, created by the backend |
| Visibility | `VisibilityScope` has no private value | A new owner-only value |
| Reads | Asset and job reads check only the tenant | Owner check on private content, otherwise `RESOURCE_NOT_FOUND` |
| Duplicates | One asset per (tenant, SHA-256), and the 409 names the existing asset | Duplicates scoped per owner, or one student learns another uploaded the same file |
| Retrieval | Filtered by tenant only | Filtered by what this user may read ([M4](mobile-m0-boundary.md#m4-retrieval-readiness)) |

Safeguards the reviewer requires:

- The backend enforces private ownership, not the mobile UI.
- Asset, job, retrieval and citation access all enforce ownership.
- Cross-student access returns the same non-disclosing response as a nonexistent resource.
- Duplicate detection doesn't reveal another student's asset or its ID.

**The duplicate rule is a security requirement.** The existing unique constraint would otherwise tell a student that a classmate holds an identical file, and give them its ID. M3-D resolves this at both the database and API levels: no response may let a student establish whether another student has uploaded a particular document.

If this can't be implemented safely within the first release, **student uploads are disabled** rather than shared visibility being introduced early: students then read and ask about staff-provided material only.

M0 needs no migration. M3-D will, and that migration needs the usual review.

## Decision C: tenant entry

**Approved: these existing routes are in the first release:** `POST /tenants/{slug}/join`, `POST /invitations/accept`.

The approved scope lists registration and memberships but no way to join. Without these, a newly registered student has no tenant and can't reach any tenant-scoped screen. Both already exist, and joining already requires a verified email. Membership stays subject to verified identity, an invitation or the join policy, and backend authorization.

## Decision D: upload read timeout

**Approved: raise `upload_read_timeout_seconds` for the mobile contract, to a value set by measurement in M3-D.**

The whole body must arrive within 60 seconds, so a full 25 MiB file needs a sustained 3.5 Mbit/s. Students on slower mobile connections would hit `UPLOAD_READ_TIMEOUT` repeatedly, with nothing resumable. The setting allows up to 600 seconds. A longer timeout holds a connection and worker capacity for longer. M3-D measures realistic upload speeds, concurrent uploads, worker capacity and timeout rates, then selects and documents a defensible value. The configuration maximum isn't a reason to choose 600 seconds.

## Where the PRD and this plan differ

PRD §7 requires conflicts to be identified.

| PRD | This plan | Handling |
|---|---|---|
| Repository `build-frontend`; mobile as a distinct surface (§21) | The PRD governs the Expo app in Build-UI | Product owner's instruction; noted in the PRD file |
| Roadmap Phases 0 to 11 include maps, offline and question generation | First release is a student subset | The PRD asks for phased delivery (§330); the rest stays on its roadmap |
| Journey C reopens a document; Journey D navigates to the source (§257) | No route returns a document's content to a student | Gap G-13; M1 must make a concrete decision. A document journey isn't complete if the product requires access to the document and students can only ask about it |
| Journey E generates practice questions (§257) | Out of the first release; students lack the permission | Later phase |
| Citation `page` in the reviewer's illustrative shape | `page_start` and `page_end`, since chunks span pages | [Citation schema](mobile-m0-boundary.md#citation-schema) |

## Kept separate

- **First deployment:** SIGTERM, a finite stop timeout above 25 s, SIGKILL and automatic restart stay a separate production gate (`docs/phase3-release-record.md`). M7 can't certify it.
- **Retrieval quality:** human review of the questions, scanned-page evaluation, and the dense, hybrid and weighted comparison. A passing integration test doesn't show that BUILD AI is academically reliable.
