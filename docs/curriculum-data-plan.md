# Curriculum data plan: how real curriculum data reaches the database

**Status: plan for review.** Companion to `docs/curriculum-model-design.md` and `docs/curriculum-handbook-analysis.md`.

## 1. The rule that governs everything

`build-backend` and `ai-service` are **public repositories**. The following **must never be committed** to either: a FUTA handbook (PDF or any copy), text extracted from it, and any extracted real curriculum data (course codes with titles, units, hours, synopses for FUTA programmes). This includes test fixtures, snapshots, logs, CI artifacts and PR descriptions. Tests use **synthetic fixtures** only: invented codes and titles in the same shape.

Guards to add with the first implementation PR (proposed, not built here):
* a `.gitignore` entry for the private bundle folder name and the extraction scratch names;
* a CI grep gate that fails a PR containing a configured deny pattern (the FUTA programme code prefixes together with a unit digit pattern) outside an allow-listed synthetic fixture path;
* a pre-commit hook for the same.

## 2. The rights question (decision for the user and the reviewer)

The handbook is a FUTA document that was shared with the user. Whether BUILD may store and serve its content to students is a **rights decision**, separate from the technical design.

| Question | Why it matters | Options |
|---|---|---|
| Who owns the departmental curriculum text and the course list? | Titles, codes and units are facts; synopses are authored prose; the handbook layout is FUTA's | Treat codes, titles, units, status and level/semester as **facts needing authorisation to publish in a product**; treat synopses as **prose requiring explicit licence** |
| Who at FUTA can authorise? | An academic representative can verify accuracy; only an authorised officer can license use | Registry / Academic Planning / the Dean of the School / Senate liaison. **Named by the user** |
| What record proves it? | A G-34-style rights record: grantor, scope (codes+titles+units / synopses / handbook text), term, revocation, attribution wording, signed date | A written letter or email, filed in the private store; its id goes into `source_document.rights_record_ref` |
| What if authorisation is refused or not yet given? | The product must still work | Keep `rights_status = pending`; rows are loadable to a **non-serving** staging database only; the student flow stays on the S-02 free selection |

**Recommendation:** ask for authorisation for *codes, titles, units, status, level, semester, entry-mode rules* first (needed for correct course lists), and treat synopses as a separate, later licence (needed for grounded tutoring text). No row is published without a `rights_record_ref`.

## 3. Where the real data lives

| Artifact | Location | Notes |
|---|---|---|
| Raw handbook PDF | **Private object-storage bucket** (access limited to the operator and the verifier), referenced by `source_document.storage_uri` with its SHA-256 | Never in git. Never on a developer laptop beyond a working copy that is deleted after extraction |
| Extracted text (scratch) | Local scratch directory outside any repo | Deleted after the candidate bundle is produced; the bundle records the extraction tool and version |
| **Candidate bundle** (normalised, flagged data) | Private bucket, versioned file (JSON) with a checksum | The exchange format between importer and verifier |
| **Verified bundle** | Private bucket, signed off by the verifier | What the loader reads |
| Production database | Rows created by an **operator command** (`python -m app.cli curriculum load --bundle <uri> --rights-record <id>`) with no HTTP route | The command refuses a bundle whose rights record or verification is missing |
| Synthetic fixtures | In the repo under `tests/fixtures/curriculum_synthetic/` | Only these may be committed |

The private seed store is **a bucket, not a repository**: cloud staging already uses object storage (the `m3d` ownership work), so no new infrastructure type is needed. A private git repository is an alternative; the reviewer chooses.

## 4. The pipeline: extract, normalise, flag, verify, publish

```text
 1 EXTRACT      PDF (private bucket) ──pdftotext -layout──> scratch text      [python -I, no execution of content]
 2 NORMALISE    deterministic parser ──> candidate rows (code normalised, status, level, semester, units, hours)
 3 FLAG         validators attach flags + confidence per row/field
 4 RECONCILE    section 7 (outline) vs section 8 (synopsis); totals vs row sums; framework pre-fill
 5 HUMAN VERIFY verifier compares candidate with the printed document, edits, accepts or rejects row by row
 6 PUBLISH      loader (operator command) creates revision, entry rules, aliases; publish gate checks
```

### 4.1 Extraction
`pdftotext -layout` is the baseline. It is **explicitly low-confidence** (analysis §4). The importer also keeps the PDF page number for each candidate row so the verifier can see the printed page next to the candidate. An OCR or vision pass (ai-service, provider-independent in the sense that the provider is a deployment choice and is **not** part of this work) may be added later as an *independent second reading*; disagreement between two readings is itself a flag.

### 4.2 Normalisation (deterministic, no AI authority)
Decode explicitly (the extraction is Windows-1252); strip page numbers and form feeds; normalise codes; parse semester headings tolerantly; split fused hours-and-units strings **into candidate readings (not a single guess)**; link a code to its section-8 entry by normalised code.

### 4.3 Flags (every flag is data, none is silently resolved)
`missing_title`, `missing_status`, `missing_code`, `missing_hours`, `missing_units`, `fused_hours_units` (with the alternative readings), `wrapped_cell`, `page_number_in_table`, `blank_total`, `total_mismatch`, `unit_mismatch_outline_vs_synopsis`, `title_mismatch_outline_vs_synopsis`, `code_prefix_drift`, `dual_code`, `code_level_mismatch`, `orphan_synopsis`, `orphan_outline_row`, `duplicate_in_revision`, `non_taught_candidate` (project, industrial training), `unknown_owner`, `status_ambiguous`.

**Confidence** is a derived number for ordering the verifier's queue, never an input to publishing. A row with any `missing_*` flag has confidence ≤ 0.3. The two sections agreeing on code, title and units raises confidence; a row agreeing on all three and with a matching semester total is `high`, still `unverified` until a human accepts it.

### 4.4 Human verification
* **Verifier:** a FUTA-authorised academic representative (for example the departmental curriculum officer or exam officer), named by the user. **Separate from legal review**: the legal reviewer confirms the rights record, the academic verifier confirms accuracy. Neither stands in for the other.
* **Method:** a review screen or sheet showing, per row, the candidate, the flags, the page image, and accept / edit / reject. Edits are stored as edits (old value kept). Verifying a row writes an append-only `verification_record` (subject, status, verifier id, role, date, evidence reference).
* **Verification units:** per revision, per level-semester table, per entry rule. A table cannot be verified while a flagged row in it is unresolved.
* **Four-eyes** for the first revision: two verifiers, or one verifier plus the reviewer's spot check of ten percent of rows.

### 4.5 Publish gate (loader refuses unless all hold)
* rights record present and covers the fields being published;
* every row `verified` (no `unverified`, `in_review` or `rejected` rows in the revision);
* semester totals match, or a verifier-recorded waiver with a reason exists;
* no duplicate code in a revision; alias collisions resolved;
* entry rules present for every entry mode the programme admits, with sources;
* admission range does not overlap another published version of the programme;
* the revision diff against the previous revision has been viewed (recorded);
* `content_sha256` computed and stored.

### 4.6 What verification cannot fix
If the printed document is itself inconsistent (the analysis shows outline vs synopsis disagree in places), the verifier chooses the correct value **with a written source** (the department's approved document, a signed correction) and the choice is recorded. If no authoritative answer exists the row stays unverified and is not served.

## 5. Bundle format (private; shape only)

```text
bundle {
  schema_version, created_at, tool{name,version},
  source_document{ title, issuer, version_label, cover_session_from/to, sha256, storage_uri, rights_record_ref },
  programme{ code, award },
  version{ label, effective_from_session, effective_to_session? },
  entry_rules[ { entry_mode, start_level, normal_semesters, max_semesters, min_units, min_cgpa, audit_codes[], required_categories[] } ],
  courses[ { normalized_code, owner_department_code, printed_code, printed_title,
             level, semester, status, units, hours{l,t,p}, category, group?, applies{utme,de},
             framework_code, source_ref{page,table,row}, flags[], confidence, verification } ],
  aliases[ { course, alias, kind } ],
  requisites[ ... ],         // empty unless the source supplies them
  synopses[ ... ]            // separate licence (§2)
}
```
The bundle schema and a validator live in the repository (so they are reviewed). Bundles do not.

## 6. Roles and responsibilities

| Role | Who | Does |
|---|---|---|
| Rights grantor | A FUTA officer named by the user | Signs the rights record (scope, term) |
| Academic verifier | FUTA-authorised academic representative | Verifies each table against the printed document; records waivers |
| Legal reviewer | Separate from the verifier | Confirms the rights record covers what is published |
| Operator | BUILD engineer | Runs extraction, produces the candidate bundle, runs the load command; cannot mark rows verified |
| Reviewer | Technical reviewer | Approves the design and each PR on its exact head SHA |

## 7. How other departments follow the same path

The same pipeline is run per department handbook. Because `course` identity is global per institution, a service course (a mathematics or general-studies code) that appears in many handbooks is verified once as a **course** (title, owner) and then per curriculum as a **row** (level, semester, status, units may differ by programme). The importer reuses an existing course when the normalised code matches and **flags a title or owner conflict** rather than overwriting.

FUTA public department pages could not be fetched from this environment (403 or bot check); once a FUTA-authorised person provides a second department's handbook, the same bundle format applies. That comparison will test which parts of the model generalise (service courses, elective groups, different entry modes). Until then the claim "this generalises" is **untested** and is marked so.

## 8. Operations

* **Idempotence:** loading the same bundle (same `content_sha256`) twice is a no-op.
* **Audit:** the load writes an audit log entry (operator, bundle id, rights record id, counts).
* **Rollback:** a published revision is never deleted; a bad load is superseded by a corrected revision. A load into staging can be rolled back by dropping the staged revision before publish.
* **Cloud-first testing:** loader and validator are tested against synthetic bundles in CI only.

## 9. Next steps

1. Reviewer approves the design; the user decides D5 to D8 in the design document.
2. User names the rights grantor and the academic verifier.
3. Build the deterministic importer and validator against **synthetic** bundles first.
4. Run the real handbook through the pipeline on an operator machine; produce the candidate bundle in the private bucket.
5. Verifier works through the queue; publish gate; staging load; student-facing flag.
