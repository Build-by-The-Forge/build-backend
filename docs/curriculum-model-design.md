# Curriculum model design: which courses does this student offer?

**Status: design for review. Nothing here is implemented. No migration and no model code until the reviewer approves.** The backend Alembic head belongs to the `m3d-uploads` lane; a revision is requested only after approval (§13).

Evidence base: `docs/curriculum-handbook-analysis.md` (separate PR) and the data plan `docs/curriculum-data-plan.md` (same PR as this file). Written against `main` at `e9067ed`, migration head `0032`. Provider-independent: no Gemini or Fireworks work.

## 0. Decisions for the reviewer and the user

| # | Decision | Recommendation | Who |
|---|---|---|---|
| D1 | Where authority for "what a student offers" lives | **The institution's published curriculum revision**, not benchmark-plus-overrides. The NUC benchmark (ADR 008) stays a provenance and diff layer. This amends ADR 008 §2 and the 4A.7/4A.8 plan | reviewer |
| D2 | What a curriculum version's dates mean | **Admission cohorts, not the session being studied.** A version applies to students *admitted* in `[effective_from, effective_to)` | reviewer |
| D3 | Content changes vs applicability changes | Two layers: **version** (who it applies to) and immutable **revision** (what it says). Corrections publish a new revision, never an edit | reviewer |
| D4 | Provenance granularity | **Per curriculum row** (framework + source document + row verification). Level-band mapping is only a reviewer convenience | reviewer |
| D5 | "BCCMAS" | Recorded as `reported-by-user`, expansion **unknown**. No band is marked verified until a FUTA-authorised person supplies the document | user |
| D6 | Unverified rows | **Never served as authoritative.** Onboarding falls back to today's free selection and says so. An explicit, flagged "provisional" mode for a pilot is an option | user + reviewer |
| D7 | Rights to FUTA curriculum data | Real data stays out of git. Needs a FUTA authorisation record (G-34 style) before loading even to a private store | user |
| D8 | Who verifies | A FUTA-authorised academic representative (department curriculum officer), separate from legal review | user |
| D9 | Carry-overs and audits in R1 | Model the **resolver output** for them now; defer the full student result history (no results product in R1) | reviewer |
| D10 | Student binding | Bind at admission by rule; allow an audited **re-binding** event (mid-programme migration of a cohort) | reviewer |

## 1. Principles

1. A student's **admission session** (plus programme and entry mode) selects a curriculum version. The resolver **never silently returns the latest** version.
2. Nothing published is edited. Change = new revision (content) or new version (applicability).
3. Provenance is data: every row can answer "which framework, which document, who verified, when".
4. Unverified data is representable and visible, but is not served as truth.
5. CCMAS alone is never assumed to be a university's complete curriculum: the institutional revision carries FUTA-specific rows, extension levels and service courses explicitly.
6. A course has one global identity per institution (normalised code) and may be consumed by many curricula and cross-listed under other codes.
7. Handbook-scoped facts (durations, graduation units, audits) are **per version and per entry mode**, because they differ by route and change over time.
8. Everything is tenant-scoped; no query crosses tenants.

## 2. Entity overview

```text
institution (tenants, exists)
  ├─ faculty / department (exist; org-unit history only as a name snapshot, §3.1)
  │    └─ programme (exists)
  │         └─ curriculum_version (extend)           WHO it applies to (admission cohorts)
  │              ├─ curriculum_revision (new)        WHAT it says (immutable once published)
  │              │    ├─ curriculum_course (new)     row: level, semester, status, units, hours, entry modes, provenance
  │              │    │    └─ curriculum_course_requisite (new)
  │              │    └─ curriculum_group (new)      elective choice sets
  │              ├─ curriculum_entry_rule (new)      per entry mode: start level, durations, graduation rules
  │              └─ level_band_framework (new)       user-reported / verified defaults
  ├─ course (exists)  ── course_alias (new) ── course_synopsis (new)
  ├─ curriculum_framework (new) ── source_document (new)
  ├─ verification_record (new, append-only)
  └─ student side: academic_profile (extend) ── student_curriculum_binding (new) ── student_course_flag (new)
```

## 3. Entities in detail

Columns are proposals. All new tables carry `id`, `tenant_id` (composite FKs as in migration 0032), `created_at`, `updated_at`. Enumerations are `String` with a CHECK, matching the repository's convention.

### 3.1 Institution, school, department, programme

* **Institution = existing `tenants`.** No change.
* **Faculty/school and department: existing.** FUTA's public repository shows schools were regrouped over time (analysis §5). Do **not** model organisational history now. Store `school_name_as_printed` and `department_name_as_printed` on `source_document` and on `curriculum_version` as snapshots so a historical handbook stays readable after a regrouping.
* **Programme: existing** (`name`, `code`, `duration_years`). Add: `award` (e.g. `B.Tech`), nullable. `duration_years` becomes a display default; **authoritative durations move to `curriculum_entry_rule`** (§3.6) because they differ by entry mode and version.
* **Admission requirements** are structured data on the entry rule: `admission_requirement` JSON `{route, rules:[{kind: subjects|credits|alevel|nd|nce, …}], text}` plus the printed text. Only the text is required to publish; structure is optional and never used to gate a student.

### 3.2 Curriculum framework and source document (provenance)

`curriculum_framework`

| Column | Notes |
|---|---|
| `code` | `CCMAS`, `BMAS`, `INSTITUTIONAL`, `BCCMAS` (the last exactly as reported; see below) |
| `name`, `issuer` | issuer: `NUC`, `FUTA Senate`, … |
| `expansion_status` | `verified` / `reported_by_user` / `unverified` |
| `notes` | |

`BCCMAS` is created with `expansion_status = reported_by_user` and **no document**. If it later turns out to be a FUTA-modified extension, a different framework row is added and rows are re-pointed by a verification record, never by silent update.

`source_document` (links to the existing `curriculum_snapshots` where a snapshot exists)

| Column | Notes |
|---|---|
| `framework_id` | nullable until known |
| `title`, `issuer`, `version_label`, `published_on` | `published_on` nullable: handbook cover years are a **cover window**, not a date |
| `cover_session_from`, `cover_session_to` | text, e.g. `2025/2026`; informational only |
| `url`, `accessed_on` | public sources only |
| `sha256`, `storage_uri` | for private sources the URI points at the private store, never a repo path |
| `rights_status` | `public` / `authorised` / `pending` / `refused` |
| `rights_record_ref` | pointer to the authorisation record |
| `extraction_tool`, `extraction_version` | for reproducibility |

`level_band_framework(curriculum_revision_id, level_from, level_to, framework_id, verification_status, source_ref)`: the user's "100–200 follows CCMAS, 300–500 follows BCCMAS" is stored **once, as `reported_by_user`**. Importers may pre-fill row `framework_id` from it; rows still need their own verification, and the analysis shows the pre-fill would be wrong for some 300 level rows.

### 3.3 Curriculum version and revision

**`curriculum_version`** (extend the existing table, which already has `programme_id`, `name`, `version`, `effective_session_id`, `expires_session_id`, `status`)

| Column | Change |
|---|---|
| `effective_session_id` | **meaning changed to first admission session covered** (inclusive) |
| `expires_session_id` | **last-covered admission session + 1** (exclusive), nullable = open |
| `framework_id` | new: the dominant framework (display only; provenance is per row) |
| `supersedes_version_id` | new, nullable |
| `status` | extended: `draft`, `candidate`, `verified`, `published`, `superseded`, `withdrawn` (existing `active`/`archived` map to `published`/`superseded`) |
| `verification_status` | `unverified` / `in_review` / `verified` / `rejected`, derived from the latest `verification_record` |
| `course_ids` text blob | **deprecated**; replaced by `curriculum_course`. Kept read-only until backfill is complete |
| `school_name_as_printed`, `department_name_as_printed` | snapshots |

Invariants: (a) per programme, **published versions' admission ranges must not overlap** (exclusion constraint on the ordered session start dates, or an application check inside the same transaction); (b) a published version cannot be deleted; (c) `status=published` requires `verification_status=verified`.

**`curriculum_revision`** (new): `curriculum_version_id`, `revision_no`, `status` (`draft`/`candidate`/`verified`/`published`/`superseded`), `source_document_id`, `published_at`, `content_sha256`, `change_note`. Unique `(version, revision_no)`. A published revision is **immutable**: a correction creates revision *n+1* by copy. Exactly one revision per version is `published`; the resolver picks it. Student-facing records that matter later (CBT attempts, mastery, tutoring citations) store the `revision_id` they used (ADR 008 §6).

### 3.4 Course, aliases, synopsis

**`course`** (exists: `tenant_id`, `department_id` = owning department, `code`, `title`, `credit_units`, `level`, `semester`, `status`; unique `(tenant, code)`).

* Add `normalized_code` (upper-case, spaces removed), unique per tenant. The existing `code` stays for display. Backfill from `code`.
* `credit_units`, `level`, `semester` on `course` become **non-authoritative defaults** ("what the catalogue last showed"). The authoritative values live on `curriculum_course`. They stay for backward compatibility with `/academic/profile` and are deprecated in the contract (§10).
* **Owning department** is explicit and stored; code prefix is only an import hint. A service course is a course whose owner differs from the consuming programme's department; nothing special is stored for it.

**`course_alias`**: `course_id`, `alias_code` (normalised), `kind` (`cross_list` / `renumbered` / `printed_variant` / `dual_code`), `valid_from_session`, `valid_to_session`, `source_ref`. This resolves the dual-code project course, a course printed under two prefixes, and prefix-drift typos found in the handbook. Lookup by any alias returns the same `course_id`. An alias that could name two different courses is rejected.

**`course_synopsis`**: `course_id`, `source_document_id`, `text`, `lab_text` (nullable), `verification_status`, `language`. Learning outcomes continue to live in the existing topic/outcome tables; a course with a synopsis but no outcomes is allowed and labelled.

### 3.5 Course in curriculum (the central table)

**`curriculum_course`** (one row per course per revision)

| Column | Notes |
|---|---|
| `revision_id`, `course_id` | unique together |
| `level_code` | 100…600 (matches `levels.code`) |
| `semester_no` | 1 or 2 (matches `semesters.number`) |
| `status` | `core` (C), `required` (R), `elective` (E) as printed |
| `status_detail` | `university_required` / `school_required` / `compulsory_elective` / `optional_elective` / `null` when the source does not say |
| `credit_units` | integer ≥ 0 (**zero allowed** for audit rows) |
| `hours_l`, `hours_t`, `hours_p` | handbook convention (per week); nullable |
| `hours_lecture_sem`, `hours_practical_sem` | NUC convention (per semester); nullable. Store whichever the source gave; do not convert silently |
| `applies_utme`, `applies_de` | booleans (entry-mode applicability). Direct Entry at 200 level does not need rows at 100 level marked `applies_de=false`; the entry rule's `start_level` already excludes them. Use the flags only for rows that genuinely differ by route |
| `is_audit` | zero-unit, must-pass-at-first-sitting rows for Direct Entry |
| `counts_to_cgpa` | false for audit and optional-elective rows when the source says so; null when it does not |
| `category` | `general_studies` / `faculty` / `programme` / `siwes` / `project` / `service` / `elective` (for graduation category sums) |
| `group_id` | elective choice set (§3.7); nullable |
| `printed_code`, `printed_title` | exactly as printed; `course.title` may differ |
| `framework_id` | **this row's framework** |
| `source_document_id`, `source_ref` | document and page/table/row pointer |
| `benchmark_course_id` | nullable link to the ADR 008 `benchmark_courses` row when the row derives from a CCMAS course |
| `verification_status` | `unverified` / `in_review` / `verified` / `rejected` |
| `confidence` | importer score 0 to 1 (never read by the resolver) |
| `flags` | list of importer flags (§ data plan 4) |

Unique `(revision, course)`. A course may not appear twice in a revision at different levels (a real handbook with one would be modelled as two revision rows only if the printed document says so; the importer flags it).

**`curriculum_course_requisite`**: `curriculum_course_id`, `requisite_course_id`, `kind` (`prerequisite` / `corequisite`), `min_grade` (nullable), `source_ref`, `verification_status`. Requisites are **per revision** because they change with curricula. The handbook has none, so initial data is empty and the mastery consumer treats "no requisites" as *unknown*, not *none* (§9).

### 3.6 Entry rules and graduation

**`curriculum_entry_rule`**: one row per `(curriculum_version, entry_mode)`:

| Column | Notes |
|---|---|
| `entry_mode` | `utme`, `direct_entry` (extensible: `transfer`) |
| `start_level` | 100 for UTME; 200 for Direct Entry (a fact from the handbook, a rule here) |
| `normal_semesters`, `max_semesters` | |
| `min_units` | the graduation minimum for this route |
| `min_cgpa` | |
| `admission_requirement` | JSON plus printed text (§3.1) |
| `audit_required_codes` | list of aliasable course codes, or a link to `curriculum_course` rows with `is_audit` |
| `required_categories` | JSON `[{category, min_units}]`, e.g. general studies minimum |
| `source_document_id`, `source_ref`, `verification_status` | |

Institution-wide rules (registration window, load minimum and maximum, probation threshold, resit policy, dean's list threshold, grading scale) belong in a separate versioned `institution_rule` table consumed by scoring, not by this resolver. They are named here so they are not forgotten; they are not designed here.

### 3.7 Electives, SIWES, projects

* **`curriculum_group`**: `revision_id`, `name`, `min_courses`, `min_units`, `max_units`; `curriculum_course.group_id` places elective rows in a choice set. The handbook gives no choice rules, so a group may have `min_units = null` (unknown). The resolver returns the group and its members, never picks for the student.
* **SIWES / industrial training / projects** are ordinary `curriculum_course` rows with `category` in (`siwes`, `project`) and large practical hours. Two things differ: they may span several semesters (a project taken in two semesters is two rows with two course identities, as printed) and they are *not* offered as normal taught courses to CBT/tutoring (flag `non_taught=true` in `flags`, surfaced in the read contract).

## 4. Student side

Extends the S-02 `academic_profiles` (migration 0032: `programme_id`, `level_code`, plus the course set `academic_profile_courses`).

| Column / table | Purpose |
|---|---|
| `academic_profiles.admission_session_id` | the session of admission (FK to `academic_sessions`) |
| `academic_profiles.entry_mode` | `utme` / `direct_entry` |
| `academic_profiles.current_semester` | 1 or 2, nullable until onboarding collects it |
| `student_curriculum_binding` (new) | `profile_id`, `curriculum_version_id`, `bound_at`, `bound_by` (`system_rule` / `staff` / `student_confirmed`), `reason`, `ended_at`. **Append-only**: re-binding ends the current row and inserts a new one. The *current* binding is the row with `ended_at is null`. |
| `student_course_flag` (new) | `profile_id`, `course_id`, `kind` (`carry_over` / `audit` / `exempt`), `from_session_id`, `note`. Minimal state for R1 (D9) |

**Entry level.** Entry mode gives `start_level` through the entry rule. A student who selects Direct Entry and a 100 level is inconsistent: the profile is rejected with 422 (`VALIDATION_FAILED`, field `level`), not corrected silently.

**Binding rule at admission.** On save with `admission_session_id`, `programme_id` and `entry_mode` known, the system looks up the published version whose admission range contains the session. If exactly one exists, it writes a `system_rule` binding. If none or several (a data error) exist, **no binding is written**, the profile stays usable without one, and the read contract answers `curriculum: unresolved` with a reason code (§5.3).

**Existing profiles (backfill).** Profiles already saved have no admission session. They get no binding and keep today's behaviour. The client asks for the session at the next onboarding step. No heuristic guess (such as "level 200 means 2025/2026") is allowed to write a binding.

## 5. The query contract

### 5.1 Resolver interface (application layer, new `app/application/curriculum/resolver.py`)

```text
resolve_version(tenant, programme_id, admission_session_id, as_of=None) -> VersionResolution
courses_for_student(tenant, profile_id, level=None, semester=None) -> CurriculumListing
courses_for_cohort(tenant, department_id, programme_id, level, semester,
                   admission_session_id, entry_mode) -> CurriculumListing
```

```text
VersionResolution {
  state: "resolved" | "unresolved"
  version?: { id, label, framework_code, admission_range }
  revision?: { id, revision_no, published_at, verification: "verified" }
  reason?: "no_published_version" | "overlapping_versions" | "session_unknown"
         | "programme_unknown" | "entry_mode_unsupported" | "not_bound_yet"
}

CurriculumListing {
  resolution: VersionResolution
  level, semester
  entry_mode
  courses: [ { code, title, level, semester, status, status_detail?, credit_units,
               hours{l,t,p}?, category, owner_department{id,name}, own_department: bool,
               is_audit, counts_to_cgpa?, group?, aliases[], non_taught,
               provenance{ framework_code, source_title, source_ref_label, row_verification } } ]
  carry_overs: [ ... same shape, "from_level" ... ]      // courses_for_student only
  audit_courses: [ ... ]                                  // Direct Entry audits
  totals { units, core_units, elective_units }
}
```

### 5.2 Resolution algorithm (deterministic; the acceptance criterion)

1. **Pick the version.**
   * `courses_for_student`: use the student's **current binding** if it exists. Else compute from the profile's `(programme_id, admission_session_id)` as below. If the profile has no admission session, return `unresolved / session_unknown`.
   * `courses_for_cohort`: compute from the arguments.
   * Compute: `V = published versions of the programme whose [effective_from, effective_to) contains the admission session's start date`. `|V| = 1` → resolved; `0` → `no_published_version`; `>1` → `overlapping_versions` (a data error, alerted).
2. **Never** fall back to "the latest published version" or "the current session's version". An older student whose cohort has a version resolves to **that** version even when a newer one is published. A student with no covering version gets `unresolved`.
3. **Pick the revision:** the version's single `published` revision. (A later `published` revision changes what an old cohort sees only through a reviewed correction, by design D3. Records created earlier keep their stored `revision_id`.)
4. **Entry rule:** load the `(version, entry_mode)` rule. `level < start_level` returns an empty list with `reason = below_entry_level`, never rows from lower levels (except audits).
5. **Filter rows:** `level_code = level AND semester_no = semester`, `applies_<mode> = true`, row not `rejected`, `verification_status = verified` (§8 for the unverified path).
6. **Other-department courses are included**: ownership never filters. `own_department` is a display flag.
7. **Carry-overs** (`courses_for_student`): add the student's `carry_over` flags whose course exists in the bound revision at an earlier level/semester, marked `from_level`/`from_semester`. A flagged course that is absent from the revision is returned with `provenance.row_verification = unknown` and a note, not dropped.
8. **Audits:** rows with `is_audit` for the student's entry mode are returned separately with `credit_units = 0`.
9. **Order:** `status` (core, required, elective), then normalised code, then `id`: stable for pagination and tests.
10. **Spill-over:** a level above the revision's highest level (or semester beyond the entry rule's `max_semesters`) returns the highest-level rows with `spillover = true`; the system never invents rows.

### 5.3 Reason codes and HTTP behaviour (proposed, contract PR)

An unresolved listing is **`200` with `resolution.state = "unresolved"`**, not an error: onboarding is a normal state (same principle as S-02 decision 8). Authorization, tenancy and student-only access follow S-02 (student membership; staff get `403 PERMISSION_DENIED`).

## 6. Versioning: change without overwriting history

| Change | Mechanism | Effect on existing students |
|---|---|---|
| Typo or unit correction in the printed curriculum | New **revision** of the same version (copy, edit, verify, publish). Old revision is `superseded`, retained | Everyone bound to the version sees the correction. Records already stored keep their old `revision_id` |
| New curriculum for new entrants (e.g. next admission year) | New **version** with `effective_from = next session`; previous version's `effective_to` set to the same session (single transaction) | Old cohorts stay on the old version. New cohorts get the new one |
| Framework adoption mid-stream (e.g. a national standard applying only to new 100 level entrants) | A new version for the new cohort. Continuing cohorts keep theirs | None |
| Cohort moved to a new version (e.g. institution decides continuing students migrate) | `student_curriculum_binding` re-binding event, with `bound_by`, `reason` and approver; the old binding row is ended, not deleted | Affected students only; reversible by another event |
| Course renamed/renumbered | `course_alias` (renumbered) and a new revision row, not an update of the old one | Old revisions keep the old printed code and title |
| Course withdrawn | Absent in the new revision. The course row stays for history | Old cohorts unaffected |

Overlap and gap checks run at publish time: publishing a version fails if it overlaps another published version of the same programme, or leaves a gap *inside* a range that has admitted students (a warning, not an error, for future sessions).

**Diff.** A revision diff (added, removed, changed units, changed level/semester/status) is computed by the backend deterministically, as in ADR 008 §4. This is how the verifier sees what a new revision changes.

## 7. How the cases from the handbook are modelled

* **A course in several departments.** One `course` (owner = the department that teaches it). Many `curriculum_course` rows across programmes, one per revision. Code variants are `course_alias` rows. A dual code (a local code plus a university-wide code on the same course) is one course with an alias of kind `dual_code`.
* **Direct Entry at 200 level.** `curriculum_entry_rule(direct_entry).start_level = 200`. Direct Entry students see the same revision from 200 level upward. Their graduation minimum comes from their own rule row. Audit rows (the zero-unit lower-level courses) come from `is_audit`.
* **Change of department.** Out of scope for the resolver; a student who changes programme gets a new profile programme and a new binding (admission session stays; the new programme's version containing that session applies, or `unresolved` if none). This is a known gap (§11).
* **UTME student on the 10th semester vs maximum stay.** Spill-over rule (§5.2 step 10).

## 8. Unverified data

States for rows and revisions: `unverified` → `in_review` → `verified` / `rejected`. The resolver serves **verified** rows only. Behaviour when a version exists but is not verified:

| Mode | Behaviour | Default |
|---|---|---|
| `strict` | `resolution.state = unresolved`, reason `no_published_version`; client falls back to free course selection (S-02) | **yes** |
| `provisional` (per-tenant flag, off by default) | Unverified rows are returned with `row_verification = "unverified"` and the contract carries `provisional: true`. Mobile shows a "not yet confirmed by your department" label. CBT and tutoring must not treat these as authoritative | no |

A row that is `rejected` is never returned. A mixed revision (some verified, some not) cannot be `published`.

## 9. Downstream consumers

| Consumer | Uses | Notes |
|---|---|---|
| **Onboarding course selection** | `courses_for_student` (or `courses_for_cohort` before a profile exists) | Replaces "any readable course" (S-02 decision 3) as the *default* list, still allowing carry-over and elective additions. Falls back to the S-02 list when unresolved |
| **Academic profile (S-02)** | Adds `admission_session`, `entry_mode`, `current_semester` and a `curriculum` summary object | Additive. `PUT` accepts the new fields as optional first, required once the contract PR lands and the client ships |
| **CBT question-bank classification** | `course_id` stays the classification key. A question may also carry `curriculum_revision_id` when the topic changed between revisions | Matching across versions uses `course_id` and aliases |
| **Tutoring context** | Course, synopsis, revision, and the row's verification | Unverified synopsis rows are excluded from grounding or labelled non-authoritative |
| **Prerequisite mastery** | `curriculum_course_requisite` of the bound revision | **No requisites on file = unknown**, not "none". Mastery logic must not treat missing requisites as "free to start" without a flag |
| **Results and scoring (later)** | Units, status, `counts_to_cgpa`, graduation rule | Scoring, not catalogue, owns CGPA arithmetic |

## 10. Mobile read contract (proposal; every item here needs a contract PR)

Conventions follow `docs/mobile-api-conventions.md` and the S-02 design: tenant-scoped (`X-Tenant-Slug`), membership checked on every request, no `tenant_id`/`user_id` in responses (the schema is the allowlist), unknown input fields rejected with 422, submitted values never echoed.

| Route | Purpose | Contract PR? |
|---|---|---|
| `GET /academic/curriculum` (query: `level`, `semester`, both optional) | `CurriculumListing` for the caller | **Yes** (new) |
| `GET /catalogue/programmes/{programme_id}/curriculum` (query: `admission_session_id`, `entry_mode`, `level`, `semester`) | The cohort listing, for onboarding before a profile exists | **Yes** (new) |
| `GET /academic/profile` | Adds `admission_session {id, name}`, `entry_mode`, `current_semester`, `curriculum {state, label, framework, verification}` | **Yes** (additive) |
| `PUT /academic/profile` | Adds optional `admission_session_id`, `entry_mode`, `current_semester` | **Yes** (additive, optional first) |
| `GET /catalogue/admission-sessions` | The sessions a student can pick | Check whether an existing route already serves it; else **yes** |

Course object fields are those of §5.1. The profile's existing `courses` items keep `{id, code, title, level, semester, credit_units}`; `level`, `semester` and `credit_units` there are marked **"as resolved for the student's curriculum when bound, else the course default"**, a behaviour note, not a shape change.

## 11. Gap table: what exists vs what is needed

| Need | Exists today | Gap | Action |
|---|---|---|---|
| Institution, faculty, department | `tenants`, `faculties`, `departments` | none for R1; org history not modelled | none; snapshot names on the document |
| Programme | `programmes` (`duration_years` only) | award, per-entry-mode durations | `award`; durations in entry rules |
| Curriculum version | `curriculum_versions` with session range, status, `course_ids` text blob | cohort semantics undefined; no framework/provenance; blob instead of rows; no revisions | extend; add revisions; deprecate blob |
| Course | `courses` with level, semester, units on the course | level/semester/units are version-specific; no normalised code; no aliases | `normalized_code`, `course_alias`; defaults become non-authoritative |
| Course in curriculum | none (a doc names `ProgrammeCourse`; it was never built) | everything | `curriculum_course` |
| Prerequisites | `course_prerequisites` (course level, no version) | per-revision, provenance | `curriculum_course_requisite` |
| Framework and provenance | `curriculum_sources`, `curriculum_snapshots`, `benchmark_*` | no link to institutional rows; "BCCMAS" has no home | `curriculum_framework`, `source_document`, row provenance, `benchmark_course_id` |
| Adoption/overrides | `institutional_adoptions`, `curriculum_overrides` (4A.7 partial) | model is "benchmark plus overrides"; cannot express extension levels and service courses | D1: kept as provenance/diff; not the resolver |
| Entry modes and graduation | none | all | `curriculum_entry_rule` |
| Student admission session, entry mode, binding | profile has programme and level only | all | extend profile; `student_curriculum_binding` |
| Carry-overs, audits | none | minimal flags | `student_course_flag` |
| Verification | benchmark review fingerprint only | per-row human verification | `verification_record` |
| Resolver and read contract | none | all | resolver module; contract PR |
| Synopsis | topics and outcomes only | course synopsis with provenance | `course_synopsis` |

## 12. Self-review across every combination

Dimensions: entry mode (UTME, DE) × level (100 to 500) × semester (1, 2) × status (C, R, E) × version (old, new) × owner (own, other department) × data (verified, unverified) = 2·5·2·3·2·2·2 = **480** nominal cells. Most collapse. Each rule below says which cells it settles.

| Rule | Cells it settles |
|---|---|
| R1. Version depends only on programme and admission session, never on level, semester, status, owner | all `old/new` cells: a student keeps their version at every level |
| R2. DE `start_level = 200`: any DE × level 100 cell is empty (audit rows aside) | 1 level × 2 semesters × status × version × owner × data = 48 cells |
| R3. Owner never filters; own/other is a display flag | all owner cells |
| R4. Status is data on the row: C, R, E are all returned; E additionally exposes its group | all status cells |
| R5. Unverified rows are excluded in `strict` mode; labelled in `provisional` | all unverified cells |
| R6. Semester is 1 or 2; SIWES and industrial-training semesters are ordinary rows with `non_taught` | all semester cells |
| R7. Level above the highest revision level uses spill-over rule | level 500 and beyond |

**Combinations the handbook cannot answer** (the model can hold them; the data is missing). Each of these must stay `unverified` or `unknown` until a person supplies it:

| Combination | Why it cannot be answered from the handbook |
|---|---|
| any × *old version* | No prior version is printed. Every handbook is the "new" one; admission cohorts before its cover window have no curriculum |
| any DE row that differs from UTME at 200 level and above | One set of tables; no route-specific rows |
| 300 L semester 2, 400 L semester 1, 500 L semester 2 | Rows unrecoverable from the extraction (analysis §4.1) |
| E rows: compulsory or optional, and how many to choose | Not stated |
| R rows: university-required or school-required | Not stated |
| Requisites for any row | None printed |
| Which framework a row came from | Not stated; BCCMAS unverified |
| Owner of a course whose prefix is shared or drifts | Not stated |
| Cohort applicability | Cover years only |
| Learning outcomes | Not in the handbook |
| The sum rule for graduation units against the table totals at 300 level semester 2 | Totals do not reconcile (analysis §4.6) |

**Hazards found in the self-review, with the fix in the design:**

1. *Admission session vs study session confusion* (the likeliest bug): version dates are admission dates (D2) and the resolver never takes the current session as input.
2. *A student with no admission session*: unresolved, never guessed (§4).
3. *Overlapping versions*: publish-time exclusion check and `overlapping_versions` at read time.
4. *A cohort straddling a reform*: cohort versions are per admission session; migration is an explicit re-binding (D10).
5. *Course appears at two levels in one revision*: rejected at publish; importer flags it.
6. *Alias collision*: an alias naming two courses is rejected.
7. *Student at a level with no rows but later rows exist* (a gap in the table): returns an empty listing plus a `gap` reason, not rows from another level.
8. *Missing requisites read as "no requisites"*: explicit unknown.
9. *Zero-unit rows summed into totals*: `totals` excludes `is_audit`.
10. *A verified revision later found wrong*: new revision; old stays; stored `revision_id` records which one a student saw.

## 13. Migration plan (after approval only)

Order of additive migrations (each reversible; none touches data in a destructive way):

1. `curriculum_framework`, `source_document`, `verification_record`.
2. `course.normalized_code` (+ backfill, unique), `course_alias`, `course_synopsis`.
3. `curriculum_versions` extension, `curriculum_revision`, `curriculum_entry_rule`, `level_band_framework`.
4. `curriculum_course`, `curriculum_group`, `curriculum_course_requisite`.
5. `academic_profiles` columns, `student_curriculum_binding`, `student_course_flag`.
6. Backfill: existing `courses` (level, semester, units) become one **legacy revision** per programme marked `unverified`, framework `INSTITUTIONAL`, so the resolver has something to say about the legacy catalogue without serving it as truth.

Process: the reviewer approves the design → I ask the `m3d-uploads` lane (session local_4920aecc-ca93-4ed9-8a23-34ea1dc34ff7) for the next revision number → separate PRs per step above. CI runs in the cloud only.

## 14. Tests as specification (deliverable 4, after review)

Synthetic fixtures only (invented codes in the same shape: for example programme `Applied Foo Science`, courses `ABC101`, `ABC102`, `XYZ201`, a cross-listed pair, a dual-code project, two versions admitting 2023/2024 and 2025/2026). Strict-xfail tests pin: the admission-session-to-historical-version rule (a 2023 entrant resolves to the 2023 version while a newer version exists); no silent latest; Direct Entry start level and audits; other-department course inclusion with owner; unresolved states and reasons; unverified exclusion in `strict`; revision immutability and re-binding history. Opened as a separate draft PR once this design is approved.

## 15. Out of scope

Grading arithmetic, probation and carry-over *policy enforcement*, change-of-department workflow, timetables, fees, and any provider work.
