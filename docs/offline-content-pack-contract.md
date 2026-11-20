# Offline RAG content-pack contract (DRAFT design spec)

**Status: draft design for the reviewer. Release 2.** Release 1 has no managed packs, no lease, no sync and no offline retrieval; it caches only already-opened documents (`docs/BUILD_IMPLEMENTATION_PLAN.md` section 2.3). This design authorises no route, migration or app code.

**Builds on:**
- the approved offline authorisation design in `docs/m3-d-design.md` ("Offline AI", approved at `ab09d2c`), which this contract implements and does not change;
- the online retrieval and evidence code in `ai-service` (`app/services/rag/`, `app/core/rag/contracts.py`);
- `docs/entitlement-design.md` and `docs/study-planner-design.md` (the same tools run offline).

**Every claim about existing code cites a path.** Everything else is a proposal, marked as such.

## 1. Principles

1. **Offline takes part in the same guarantees as online.** It must not become a route around them (`docs/m3-d-design.md`, "Offline AI").
2. **The guarantee is bounded, never "authorised now".** A disconnected device cannot learn of a revocation, so the lease bounds how long it holds access.
3. **Fail closed.** No valid lease, no trusted time, a bad hash, a mismatched embedder: no protected offline use.
4. **Citations come from stored chunk metadata, never from model output.**
5. **Abstain rather than guess.** Offline answers are provisional until the server validates them.
6. **Offline reading is free; AI inference is entitled** (plan section 14.2). A pack of course material is not paywalled.
7. **One set of contracts with online:** the same chunk and citation shape, the same evidence rule, the same tool definitions.

## 2. The content pack

A **pack** is a versioned, signed, revocable bundle of course material for one scope, built by the backend from documents the user was authorised to read at build time.

### 2.1 Identity and scope

| Field | Meaning |
|---|---|
| `pack_id` | Stable id for a pack lineage |
| `version` | Monotonic integer per lineage. A device refuses to install a lower version than the floor in its lease (section 5.3) |
| `tenant_id` | The tenant. A pack never spans tenants |
| `scope` | `course` (a catalogue course) in the first design. Other scopes (a personal shelf subset) need a decision (section 12) |
| `course_id`, `level`, `semester` | As in the academic catalogue |
| `audience` | Who may hold it: the set of users the build authorised, as the one read policy decided at build time. A pack is built **per user**, not shared, so no pack carries a document the user couldn't read |
| `built_at` | Server time |
| `read_policy_version` | The version of the read policy and `denied_assets` the build used, so a later policy change can be seen as stale |

### 2.2 Manifest

The manifest is a JSON document. The backend signs it (Service Signature style, with a `key_id` so keys can rotate). The device verifies the signature before it reads anything else.

```json
{
  "manifest_version": 1,
  "pack_id": "...", "version": 7, "tenant_id": "...",
  "scope": {"type": "course", "course_id": "...", "level": 300, "semester": 1},
  "built_at": "2026-12-01T10:00:00Z",
  "read_policy_version": 41,
  "embedding": {"model": "sentence-transformers/all-MiniLM-L6-v2", "dimension": 384, "dtype": "float32"},
  "retrieval_policy": {"top_k": 5, "dense_weight": 0.7, "rrf_k": 60},
  "documents": [{"asset_id": "...", "run_number": 1, "attempt": 1, "title": "...", "sha256": "...", "chunk_count": 212}],
  "files": [
    {"path": "content.sqlite", "bytes": 0, "sha256": "..."},
    {"path": "vectors.bin", "bytes": 0, "sha256": "..."}
  ],
  "key_id": "k2026-12",
  "signature": "..."
}
```

- **`embedding`** is a hard compatibility key (section 6.2). Its values here are the online index's own: `MODEL_ID` and `DIMENSION` in `ai-service` `app/services/rag/onnx_embedder.py`, and `retrieval_policy` repeats the defaults of `RetrievalPolicy` in `app/core/rag/contracts.py` (`top_k` 5, `dense_weight` 0.7, `rrf_k` 60). The pack records them rather than assuming them.
- **`documents`** names each source by `asset_id`, `run_number` and `attempt`, the same version triple online citations carry (`Passage.citation()` in `app/services/rag/evidence.py`).

### 2.3 Integrity

- **SHA-256 per file** and per document. The device hashes every file after download and before use, and again at each open of the store (cheap check of the `content.sqlite` header hash recorded at install; a full re-hash on a schedule is a decision, section 12).
- The **manifest's signature** covers the file hashes, so a swapped file fails.
- **Downloads are resumable** by byte range, with a part hash per range, so a failure on a poor connection costs one range, not the pack.
- A pack that fails any check is **deleted, never half-used**, and the failure is reported at the next sync.

### 2.4 State machine on the device

```
available -> downloading -> verifying -> active
active -> superseded   (a newer version installed and verified)
active -> revoked      (a revocation arrived)
active -> expired      (the lease ended; data kept, access refused)
revoked -> purged      (store and index entries deleted)
superseded -> purged
```

- `expired` keeps the bytes but refuses every read, search and answer until a sync renews the lease. `revoked` deletes (section 4.2).
- Only `active` packs are searched. At most one version per lineage is `active`.

## 3. Sync

### 3.1 Request (device to backend)

`POST` an authenticated, idempotent request carrying: the device id, the installed `{pack_id, version, manifest_sha256}` list, the current lease id and the device's lease state (`valid`, `expired`, `rebooted`, `no_trusted_time`), the app version, and the installed model packs (ids and versions only).

### 3.2 Response (backend to device)

- A **new signed lease** (section 5).
- **Revocations:** a list of `{pack_id, version or document asset_id, reason}`.
- **Pack changes:** `add`, `update` (to a version) and `remove`, each with a manifest URL and a short-lived signed download URL.
- **Entitlement for model packs:** which local model packs the user may download (`none`, `smallest`, `portfolio`; `docs/entitlement-design.md`).
- The `read_policy_version` the server now holds.

### 3.3 Ordering rules

1. **Revocations apply before the new lease takes effect.** The device purges what it was told to purge, then installs the lease. A lease is never issued ahead of the purge that justifies it. (`docs/m3-d-design.md`: revocation "removes the document, its extracted text and its local index entries before the new lease is issued".)
2. **Updates are atomic.** The new version is verified fully before it replaces the old one; until then the old version stays `active`, unless a revocation names it.
3. **Sync is idempotent.** The same request twice yields the same plan.
4. **A failed sync changes nothing** except recording the failure.

### 3.4 What triggers a revocation

A document deletion, withdrawal, takedown or rights change; the loss of a membership; the removal of a course from the user's profile; an entitlement change for model packs; a re-scan verdict of `rejected`. The backend emits it from the same outbox that drives online denial.

## 4. Revocation and purge

### 4.1 Where revocation is known

Online, a revocation is immediate (`denied_assets`, the one read policy). Offline, it is known only at the next sync. The lease bounds the gap (section 5).

### 4.2 What a purge deletes

On a revocation of a document: its rows in `chunk`, its `chunk_fts` entries and its vectors, its cached text and any provisional answer's stored excerpts that quote it. On a revocation of a pack: all of those for every document in it, then the store file. A vacuum follows so freed pages don't keep the text. The purge is recorded locally, and reported at the next sync.

### 4.3 Honest limits

A purge cannot unsend what a compromised device already copied. It does not hold on a rooted or jailbroken device (section 5.4).

## 5. The authorisation lease

This section restates the approved design (`docs/m3-d-design.md`, "Offline AI") as a contract. It changes none of its rules.

### 5.1 The lease

A signed object issued at each successful sync:

| Field | Meaning |
|---|---|
| `lease_id`, `user_id`, `device_id`, `tenant_id` | Binding. A lease for another device or user is refused |
| `length_seconds` | Starts at 72 hours (259,200), a setting to be confirmed by this design (section 12) |
| `server_expires_at` | A wall-clock expiry. The wall clock can only **shorten** a lease |
| `pack_floor` | `{pack_id: minimum version}`. A device refuses to install or use a version below the floor, so an old pack can't be reinstated after a revocation |
| `entitlements` | The offline capabilities the user holds |
| `key_id`, `signature` | As the manifest |

### 5.2 Measuring time

- At sync the device records **its monotonic clock and the boot identity**: `elapsedRealtime` with the boot count on Android (and `mach_continuous_time` with the boot time on iOS). Monotonic time keeps counting through sleep and the user can't set it.
- The lease ends when the monotonic clock has advanced by `length_seconds` since the sync.
- **A reboot ends the lease.** The elapsed time can't be established after one, so the device needs a sync.
- **No trusted time, no access.** If the monotonic clock or boot identity is unavailable, unreadable, or inconsistent with what was recorded (a counter that went backwards; a boot identity that changed without a recorded reboot), protected offline use fails closed.
- **The wall clock only shortens.** The lease also ends if the wall clock passes `server_expires_at`, or moves backwards by more than a small tolerance from the latest time seen. Changing the clock either way gains nothing.
- **Expo:** the app reads these clocks through a native module. If no reliable way to read them exists, protected offline use isn't offered; it never falls back to the wall clock (`docs/m3-d-design.md`).

### 5.3 What the lease gates

Every protected operation checks the lease first: opening a synced document, searching its text, retrieving, answering, and running a local model pack under entitlement. When the lease isn't valid, each returns the same stable `OFFLINE_LEASE_INVALID` error with a reason (`expired`, `rebooted`, `no_trusted_time`, `wrong_device`), and the user is told to connect. **Offline reading of downloaded material is not paywalled**, but it is lease-gated for rights reasons, not entitlement reasons; the two are separate checks.

### 5.4 What it does not guarantee

On a device that isn't compromised, no clock change, reboot or time setting extends a lease. **It does not hold on a rooted or jailbroken device**, which can alter the app's stored state or its view of the clock. An option for the reviewer (section 12): keep the key that decrypts the pack wrapped by the server and released per lease. Even then, a compromised device that was online once can keep what it decrypted. Offline AI cannot be hard-gated either (plan section 14.2, issue 1): the entitlement gates the authorised model-pack download and the lease.

## 6. The on-device store

### 6.1 Layout

One SQLite database per `active` pack (proposed), opened read-only by the retrieval code.

| Table | Columns |
|---|---|
| `meta` | pack_id, version, manifest_sha256, embedding model and dimension, retrieval policy, installed_at |
| `document` | asset_id, run_number, attempt, title, course_id, sha256 |
| `chunk` | chunk_id (primary key), asset_id, run_number, attempt, chunk_index, page_start, page_end, text, text_sha256 |
| `chunk_fts` | an FTS5 virtual table over `chunk.text` (`content=chunk`), tokenizer `unicode61` with `remove_diacritics` |
| `chunk_vec` | chunk_id, embedding (BLOB), `float32` first; quantisation only if the device benchmark needs it |

The `chunk` columns mirror the server table `document_chunks` (`ai-service` `app/db/models/document_chunk.py`: `chunk_id`, `asset_id`, `run_number`, `attempt`, `chunk_index`, `page_start`, `page_end`, `content`, `embedding_model`). Using the same names keeps citations identical online and offline.

- **Vectors:** a flat scan over `chunk_vec` to start. At course scale (hundreds to low thousands of chunks) a flat scan is likely enough on a 4 GB device; an ANN structure or a SQLite vector extension is added only if the benchmark shows it is needed (open decision, section 12).
- **Encryption at rest:** the store is encrypted with a key held in the Android Keystore. Whether to use SQLCipher or file-level encryption is an open decision. Per-lease key release (section 5.4) would build on this.
- **Storage limits:** a pack's size is in the manifest; the app refuses a download that would pass the user's storage cap, and shows how much each pack takes.

### 6.2 The local embedder

- Queries are embedded on the device by the **same model** that built the pack's vectors. The pack's `embedding.model` and `embedding.dimension` must equal the device embedder's, **or retrieval is refused** (`OFFLINE_EMBEDDER_MISMATCH`). Vectors from different models can't be compared.
- The online index uses `all-MiniLM-L6-v2`, 384 dimensions, via ONNX Runtime (`ai-service` `app/services/rag/onnx_embedder.py`). Running the same model on the device keeps one embedding space. Whether the device can run it within memory and latency limits is a benchmark question, and so is a smaller alternative, in which case the pack is rebuilt with that model and the manifest says so.
- **The embedder is not a generative model.** It ships with the app or as a small separate download, and is not entitlement-gated, because pack retrieval without generation is reading, not AI inference (a decision to confirm, section 12).

## 7. Hybrid retrieval

### 7.1 The algorithm

The same as online (`ai-service` `app/services/rag/retrieval.py`):

1. A lexical search over `chunk_fts` and a dense search over `chunk_vec`.
2. **Reciprocal Rank Fusion:** `score(d) = w_dense / (rrf_k + rank_dense) + w_sparse / (rrf_k + rank_sparse)`, with the weights and `rrf_k` from the manifest's `retrieval_policy`.
3. The top `top_k` (5) passages, in full, numbered `[1]..[n]` with document and page span (`gather` in `app/services/rag/evidence.py`).

Offline there is no `denied_assets` list to apply at query time: revocation is by purge, so the store holds only what is currently allowed. Scope filtering is by pack.

### 7.2 The evidence rule, and why there is no score threshold as the decider

The online code states, after measurement, that **retrieval scores cannot tell an answerable question from one the material doesn't cover (the score ranges overlap), so sufficiency is decided by the citation, not by a score threshold** (`app/services/rag/evidence.py` module docstring). The offline contract therefore keeps the same rule:

- **Sufficiency:** an answer is grounded only if it cites at least one retrieved passage and cites nothing else; otherwise it is `NOT_COVERED`. This is `check_grounded` ported to the device (section 8).
- **An evidence floor, as a safety pre-check only:** if retrieval returns no candidate at all, or the best dense similarity and the lexical match are both below a calibrated floor, the device abstains **without calling the local model**. This saves cost and prevents a small model from improvising on nothing. The floor is **not** the sufficiency test and **not** a claim that a higher score means an answer. It is set from the same kind of measurement as online (a labelled evaluation set), and is a decision for the benchmark (section 12). Until measured, the floor is "no candidates".

## 8. Citations and abstention

- **Mapped from chunk metadata, never model-generated.** The model emits only passage numbers (`[1]`). The device maps each number to the stored chunk and builds the citation from `chunk` and `document` rows: `{number, chunk_id, document_id (asset_id), page_start, page_end, excerpt, run_number, attempt}`, the shape of `Passage.citation()` (`app/services/rag/evidence.py`). A number the retrieval didn't supply is rejected.
- **The recorder can't be altered by the local model.** A device-side recorder records which chunks retrieval supplied, as `RetrievalRecorder` does online (`app/services/rag/recorder.py`); `sources_used` is built from it. A citation outside it is dropped, and an answer left with no valid citation is `NOT_COVERED`.
- **Abstention text** is the same string online and offline (`NOT_COVERED` in `app/services/rag/evidence.py`). The device also abstains, with a distinct reason code, when the lease is invalid, the pack is missing or revoked, or the embedder doesn't match.
- **Nothing is streamed before the check passes**, as online (`docs/m3-d-design.md`).

## 9. Provisional answers and reconnect validation

An offline answer is **provisional**: shown to its own user, marked as such, never uploaded, shared, synced into a conversation or treated as authoritative until the server validates it (`docs/m3-d-design.md`).

On reconnect the device sends the answer's provenance (IDs only: `asset_id`, `run_number`, `attempt`, `chunk_id`), not its text. The server checks it against the **current** read policy and denial state. If it fails, the answer is withheld from sync and redacted on the device, and its IDs are kept for audit. This is the same check as the online provenance check (`ANSWER_WITHHELD`).

## 10. Shared contracts with online learning

| Shared artifact | Online | Offline |
|---|---|---|
| Chunk and citation shape | `Passage.citation()`, `document_chunks` | The `chunk` table and the same citation dict |
| Evidence rule and `NOT_COVERED` | `check_grounded`, `evidence.py` | Ported; the same text and rule |
| Provenance (`sources_used`) | `RetrievalRecorder` | A device recorder, validated on reconnect |
| Retrieval policy | `RetrievalPolicy` | The manifest's `retrieval_policy` |
| Tool definitions | The tool registry (`app/core/tools/`) | The same names, schemas and permission model, with an offline executor (`docs/study-planner-design.md`) |
| Practice questions | Online practice, kept apart from official CBT | Offline practice only if separately approved; never authoritative; provisional scores |
| Error shape | The one error shape | Stable codes: `OFFLINE_LEASE_INVALID`, `OFFLINE_EMBEDDER_MISMATCH`, `PACK_REVOKED`, `PACK_HASH_MISMATCH` |
| Entitlements | Resolved by the backend per request | Resolved at sync and carried in the lease |

**Official CBT is online-only.** No pack carries official assessment content for taking offline.

## 11. Security and tamper

| Threat | Control |
|---|---|
| A modified pack file | Per-file SHA-256 plus the signed manifest |
| A forged manifest or lease | Signature with a rotating `key_id`; device verifies before reading |
| Rolling back to an older pack after a revocation | `pack_floor` in the lease; the device refuses lower versions |
| Setting the clock back | Monotonic time and boot identity; the wall clock only shortens |
| Rebooting to get a fresh window | A reboot ends the lease |
| Copying a pack to another device or user | Lease binds user and device; per-user packs; optional per-lease key wrapping |
| A pack of documents the user could no longer read | Revocation precedes a new lease; `read_policy_version` |
| A mismatched embedder giving silent bad retrieval | Hard refusal, `OFFLINE_EMBEDDER_MISMATCH` |
| The local model inventing a citation | Citations built from stored metadata only |
| A rooted device | **Not defended**; stated in section 5.4 |

## 12. Open decisions (none is made here)

1. The lease length (72 hours is a starting value) and the tolerance for backwards wall-clock movement.
2. Per-lease key wrapping, and SQLCipher versus file-level encryption.
3. Whether the local embedder is entitlement-gated (this design says not, as reading).
4. Pack scope beyond a course (a personal shelf subset), and per-user build cost and storage.
5. Flat scan versus an index, set by the device benchmark.
6. The evidence floor value, from an evaluation set.
7. How often to re-hash a pack in full.
8. The embedding model on device, if MiniLM doesn't fit; this forces a rebuild of packs.
9. Whether offline practice ships at all in R2 (separate approval).

## 13. Acceptance tests (before any pack ships)

- **Manifest and files:** a tampered file, a tampered manifest and a wrong `key_id` are each refused; a partial download resumes by range and a bad part is re-fetched.
- **Revocation:** a revoked document's chunks, FTS rows and vectors are absent after the purge, and the purge precedes the new lease in every ordering.
- **Lease:** a reboot ends it; a backwards counter, a missing boot identity and an inconsistent one each fail closed; moving the wall clock forward then back gains nothing; no trusted time means no access.
- **Rollback:** installing a version below `pack_floor` is refused.
- **Parity:** on the labelled evaluation set, offline hybrid retrieval returns the same top-5 as online for the same index within a stated tolerance (the tolerance and the set are decisions).
- **Grounding:** an answer with no valid citation is `NOT_COVERED`; a citation outside the recorder is dropped; no citation text comes from the model.
- **Abstention:** no candidates, an invalid lease and a mismatched embedder each abstain with the right reason code and call no model.
- **Reconnect:** a provisional answer whose source was revoked while offline is withheld and redacted.
- **Device:** memory, latency, storage and battery are measured on named real devices (an emulator doesn't count); the 4 GB RAM and 100 MB app-size requirements are checked with packs and models as separate downloads.

## 14. Delivery (proposed order, none authorised)

1. This contract approved, with the open decisions in section 12 settled or deferred.
2. The manifest and lease schemas, with a signature library and unit tests on both sides.
3. The server-side pack builder (per user, read-policy aware) and the sync endpoint, with PostgreSQL tests.
4. The native clock module and the lease checks on the device.
5. The on-device store, FTS and flat-scan retrieval, with the parity test against online.
6. The recorder, the grounding check and abstention on the device.
7. Reconnect validation on the backend.
8. Device benchmarks, then the model-pack download and its entitlement.
