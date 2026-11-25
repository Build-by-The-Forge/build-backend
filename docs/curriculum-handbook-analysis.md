# Curriculum handbook analysis: what a FUTA departmental handbook holds, and how reliable the extraction is

**Status: analysis for review.** Nothing here is implemented. It is the evidence behind `docs/curriculum-model-design.md` (separate PR).

**Rights rule for this document.** `build-backend` is a public repository. This document is a *structural* inventory. It deliberately contains **no FUTA course codes with titles, no unit values per course, no synopses and no handbook prose**. Where an example is needed it points at a line in the reviewer's private scratch extraction (`dts.txt`, regenerated on demand, never committed) or uses an invented example. Programme-level rules (durations, graduation thresholds, probation) are quoted as *facts the model must be able to hold*, and are flagged in the rights decision of the data plan (`curriculum-data-plan.md`).

## 1. Source and method

| Item | Value |
|---|---|
| Source | Departmental student handbook for one FUTA B.Tech programme (School of Computing, Department of Data Science), cover years 2025 to 2030. Supplied by the user. The user's file name calls it a "Modified Curriculum". |
| Copy used | The 617 KB copy. A second copy with the same name minus the suffix is 0 bytes and was ignored. |
| Extraction | `pdftotext -layout` into a scratch file, 1,607 lines. The PDF was treated as untrusted data. Nothing in it was executed. Any Python that reads it must run as `python -I`. |
| Line references | `L<n>` means line *n* of that scratch file. They are for the reviewer's private re-check only. |
| Verification state of everything below | **Extraction is a low-confidence source.** Facts marked "extraction-only" have not been checked against the PDF's page images or by a FUTA-authorised person. |

Encoding: the extraction is not valid UTF-8 (Windows-1252 dashes, quotes and apostrophes appear as the replacement character; e.g. L10, L18, L102, L242, L417). A pipeline must decode explicitly and keep the raw bytes' checksum.

## 2. Structural inventory: every field a curriculum database needs, and where it appears

Section numbers are the handbook's own.

| # | Handbook part | Fields it carries | Model need |
|---|---|---|---|
| 1.0 | Degree programme | Award type and name (B.Tech), programme title | `programme.award`, `programme.name` |
| front matter | Title page, preface | University, school, department, handbook years (a **cover window**, not an applicability rule) | `source_document` metadata; **not** `effective_from/to` |
| 2.0 | Philosophy, unique features, employability skills | Free text | `programme.description`; never a query field |
| 3.0 | Programme objectives | Lettered list | `programme_objective[]` (optional) |
| 4.0 | Admission requirements | Two entry routes: UTME (subjects, five SSC credits in at most two sittings, named subject set) and Direct Entry (A-level, ND, NCE alternatives with grade floors and subject pairs) | `admission_route` rows with structured `requirement` rules; free text kept alongside |
| 5.0 | Duration | Normal duration in semesters per route, maximum stay per route | `programme_entry_rule` (`normal_semesters`, `max_semesters`) per entry mode |
| 6.0 | Graduation | Pass all core / university-required / school-required courses and electives; **minimum units per entry mode**; minimum CGPA; a Direct Entry audit clause naming zero-unit lower-level courses that must be passed at first sitting, otherwise counted | `graduation_rule` per curriculum version and entry mode; `audit_course` list |
| 7.0 | Course outlines | One table per level and semester: code, status (C/R/E), title, hours (L T P), units, semester total | The core table: `curriculum_course` (see design) |
| 8.0 | Synopses | Per course: code, title, units, free-text content, sometimes a "lab work" paragraph | `course_synopsis` with provenance; learning outcomes are **absent** in this handbook |
| later | General academic regulations | Registration window, add/drop deadline, load min and max, lower-level outstanding courses first | `institution_rule` (versioned), not per curriculum |
| later | Examination regulations | Attendance threshold, CA/exam weights, offences | Out of scope for the curriculum database |
| later | Change of department | Eligibility rules | Out of scope; affects student history (see design §7) |
| later | Unit course system | Definitions: core, compulsory elective, optional elective, university required, audited, prerequisite, co-prerequisite; unit equals one lecture hour per week, or three to four lab hours | `course_status` vocabulary; hours-to-unit rule |
| later | Computation | TLU, CLU, TCP, CCP, GPA, CGPA formulas; 5-point scale | `grading_scheme` (versioned, institution level); consumed by scoring, not the catalogue |
| later | Probation, carry-over, resit, Dean's list | Probation threshold on CGPA, probation load cap, no resits, failed courses carried to the same semester next year, Dean's list threshold | `institution_rule`; carry-over is a **student-side** concept |
| later | Audit guidelines | Exemption or audit of university-required courses, no effect on class of degree | student-side `audit` record |

### 2.1 The course row (section 7) in detail

A row in a section-7 table has these fields, and a curriculum database needs every one of them **on the join between a curriculum version and a course, not on the course itself**:

| Field | Observed form | Notes |
|---|---|---|
| Code | Three letters, a space, three digits (a **four-letter** prefix also occurs) | Normalise by removing the space and upper-casing. The first digit is *usually* the level, but see §4.5 |
| Status | One letter: `C` (core), `R` (university or school required), `E` (elective) | The unit-course definitions add more states than the table uses (§2.2) |
| Title | Free text, often wrapped over two lines | Title can differ between section 7 and section 8 for the same code |
| Hours | Three digits **L T P** per week (lecture, tutorial, practical), run together or space-separated | The NUC document uses a different convention: **LH** and **PH** hours per semester (15 weeks) |
| Units | One digit | The handbook's own definition ties unit to hours |
| Semester total | A number under each table | Doubles as a validation checksum |
| Level and semester | From the table heading, not the row | Heading is the only place it exists, so heading loss is data loss |

### 2.2 Vocabulary the handbook defines vs uses

Defined: core, compulsory elective, optional elective, university required, audited, prerequisite, co-prerequisite. Used in tables: **C, R, E only**. Consequences:

* `R` is ambiguous between "university required" and "school required" (the graduation clause names both).
* `E` does not say whether it is a *compulsory* elective (counts to class of degree) or *optional* (may not count). **Cannot be answered from the handbook.**
* "Audited" is not a table status. It lives in the graduation clause for Direct Entry students.
* The definition list repeats one definition twice (L1435 repeats the university-required text under "prerequisite"; L1437 then defines prerequisite properly): a copy error, i.e. the handbook itself is not clean.

### 2.3 Fields the handbook does **not** contain

| Missing | Effect |
|---|---|
| Prerequisite and co-requisite per course | Defined in words only (L1435 to L1438); no course lists one. `prerequisite mastery` cannot be seeded from this source |
| Learning outcomes | Synopses are content paragraphs only; the public NUC document does carry outcomes per course |
| Which entry mode takes which course | Only implied: Direct Entry starts at 200 level and skips the 100 level table |
| Which cohort the tables apply to | Only a cover window (a range of years); no admission-session statement |
| Which framework each row came from | Not stated anywhere (see §5) |
| Course owner (department) | Implied by the code prefix only |
| Elective selection rules (how many electives, from which set) | Not stated |
| Prior versions | None |

## 3. Which rows are owned by other departments

The department's own prefix is the programme's code prefix. Other prefixes in the tables, grouped by the kind of owner (counts are for the extraction; unit totals deliberately omitted):

| Prefix family | Kind | Where it appears |
|---|---|---|
| `COS`, `CSC`, `CYB` | Other department in the same school (Computing, Cyber Security) | 100 to 500 level |
| `MTH`, `MTS`, `PHY`, `STA` | Other school (Sciences / Physical Sciences) | Mostly 100 and 200 level |
| `GST`, `GNS` | University general studies | 100 to 300 level; the `GNS` family is a different code prefix from `GST` for what looks like the same service band (§4.4) |
| `ENT` | Entrepreneurship (university general) | 200 and 300 level |
| `FMEE` | Engineering school service course | 100 level |
| `CSP` | Agriculture (department code reused as a prefix) | 200 level, second semester, a practical |
| `INS` | Management/project service | 400 level |

Design consequence: a course's **owning department** is a property of the course; the department that *consumes* it is a property of the curriculum row. Prefix is a good default for the owner but is not authoritative (a four-letter prefix, `FMEE`, shows prefixes are not even constant length; and the same department code `CSP` is also a prefix for a practical here). The model must store the owner explicitly.

## 4. Data-quality problems in the extraction

Counts below are from the reviewer-private scratch file. Each is a **reason the importer must flag, never fill in.**

### 4.1 Rows with missing fields
* A code and hours but **no title and no status**: L195 and L197 (300 level, second semester), L209 (a code with hours but no title and no status), L219 to L236 (400 level, first semester: codes printed in one block, titles and statuses in another).
* A status and title but **no code and no hours**: L202 to L204 (two rows), L212 (a row whose only number is a stray "20"), L286 (500 level second semester, a title with no code).
* A code but **no title and no hours**: L279 (500 level second semester).
* Result: at least **three levels** (300 second semester, 400 first semester, 500 second semester) cannot be reconstructed from the extraction alone.

### 4.2 Merged and ambiguous columns
* L T P U digits fused into one four-digit string with no spaces: all of 500 level (L251 to L288), where the header itself reads "LTPU". A string such as "1102" is ambiguous between several L/T/P splits.
* Spaced digits that can be read two ways: L162 and L206 (four numbers where the title ends in a number-like token).
* The 400 level header (L241) has the P and U columns merged; the second semester's industrial-training rows show hours and units as two numbers apart.
* A header line wrapped so that the word "Code" is on its own row (L251 to L252); a code wrapped over two rows (L257, L277).

### 4.3 Missing or damaged structure
* Page numbers and form feeds appear **inside** tables (L136, L191, L248): the importer must strip them or they become rows.
* Semester totals: one total is empty (L214, 300 level second semester); one sits on a separate line from its label (L133 to L134). Totals are the only checksum, so a missing total removes the check for that semester.
* Heading text varies ("Second Semester 300 L", L192; "Course Code  Status Course Title  LT P U"): semester headings must be parsed tolerantly, never by exact match.
* The synopsis section (section 8) starts at L290 and has no level or semester heading at all.

### 4.4 Internal contradictions between section 7 (outline) and section 8 (synopsis)
The two sections disagree, so neither is trustworthy alone. Examples by kind (line numbers in the private file):
* **Same code, different unit value** between outline and synopsis: at least five codes across 100 to 300 level (compare L146 with L639; L158 with L510; L196 with L742).
* **Same code, different title:** the 500 level codes are renumbered between section 7 and section 8 (compare L277 to L286 with L1036 to L1202); the synopsis list contains a code with a **typo in the prefix** (L1114).
* **Prefix drift for what is one course:** a mathematics code appears as `MTS` in the outline (L168, L170) and `MTH` in the synopsis (L654, L661).
* **Codes in section 8 that are in no section 7 table:** a general-studies code at L376; the engineering code `MEE 101` named in graduation (L103) has no course row at all.
* **Contradictory unit text within one entry:** L974 prints two different unit values for the same course.
* **Combined entry:** the three industrial-training rows share one synopsis (L930).
* **Dual codes:** a final-year project carries two codes joined by a slash in the outline (L257 to L258, L277 to L278) and in the synopsis (L998, L1007). The same course is therefore known by two codes (a local one and a university-wide one). Cross-listing must be a first-class concept.
* A **cross-listed code with a different department's prefix** in a synopsis heading (L1073).

### 4.5 Code and level do not always agree
Two 200-level codes appear in the 300 level first-semester table (L178, L180). So **the first digit of a code is not the level the student takes it at**; level and semester must come from the curriculum row.

### 4.6 Semester total arithmetic checks (the only internal checksum)
* Eight of the ten level-semester totals match the row sums when read as written (one of those eight only if the title-less row at L279 carries no units). The 300 level second semester total is blank and the 400 level first semester is too scrambled to sum.
* The Direct Entry minimum equals the UTME minimum less the 100 level unit total (checked). That supports the reading that Direct Entry skips the whole 100 level table.
* The nine readable totals leave a remainder for the 300 level second semester that is **smaller than the unit sum of the rows extracted there**. Either some rows are alternatives (electives to choose among), or the extraction merges two tables. This is the single most important unresolved arithmetic question; a human must resolve it from the printed page.

### 4.7 Section 7 vs the public NUC document
The public NUC Computing CCMAS document (§5) contains a B.Sc. Data Science programme whose philosophy, objectives and many course codes in the 200 and 300 level tables (code families `DTS`, `GST`, `ENT`, `CYB`, `COS`) coincide with this handbook. **The handbook is clearly a derivative of CCMAS for those rows.** It is a five-year, 168-unit B.Tech, while the NUC Computing programme is four years and 120 units, so the 400 level (industrial training semester) and 500 level are FUTA-specific extension rows. This matters for BCCMAS (§5): provenance has to be **per row**, not per level band.

## 5. CCMAS, BMAS and "BCCMAS": what is verified

Access date for every web fact below: **2026-11-25**. Public pages only; no logins; no bypass of bot checks.

| Claim | Status | Source |
|---|---|---|
| NUC CCMAS ("Core Curriculum and Minimum Academic Standards") replaces BMAS; restructuring began in 2018; unveiled December 2022 | **verified** (NUC page) | https://nuc.edu.ng/?p=4427 |
| 17 disciplines, 238 programmes; 70 percent core, 30 percent for the university's own senate; a student carries 30 to 48 credit units per session | **verified** (NUC page) | https://nuc.edu.ng/?p=4427 ; also https://newcitizen.ng/nuc-to-allow-universities-decide-30-of-their-curriculum/ |
| Implementation start September 2023; BMAS in use since 2007 with 12 disciplines | **reported** (a news article, not NUC) | https://www.withinnigeria.com/news/2023/08/23/implementation-of-new-varsity-curriculum-begins-september-2023-nuc/ |
| One NUC PDF per discipline, listed on the NUC index; Data Science sits **inside the Computing document**, not a separate file | **verified** | https://www.nuc.edu.ng/ccmas/ ; https://www.nuc.edu.ng/wp-content/uploads/2026/03/Computing-CCMAS-2023-FINAL.pdf |
| The Computing document defines UTME (four sessions) and Direct Entry into 200 level (three sessions), 120 and 90 minimum units, minimum CGPA 1.00, a general-studies block, SIWES as 3-unit courses after 200 and 300 level, a final-year project, and per-course status, units, lecture hours and practical hours | **verified** (read from the PDF text) | same PDF |
| **"BCCMAS" exists as a named NUC or FUTA framework** | **unverified. No source found.** Searches for the term returned only CCMAS documents. The NUC discipline index, the NUC announcement and the Computing PDF do not use it | web searches 2026-11-25; the pages above |
| "100 and 200 level follow CCMAS, 300 to 500 follow BCCMAS" | **reported-by-user**; the handbook does not say it (§2.3) | the user |
| FUTA public pages (main site, department sites, library site, WASCAL document) | **could not be read**: HTTP 403 or a bot-verification page, including in the in-app browser. Nothing was bypassed | https://www.futa.edu.ng ; https://csc.futa.edu.ng/home/courses/400 ; https://sen.futa.edu.ng/home/2669 ; https://ifs.futa.edu.ng/home/2672 ; https://soclibrary.futa.edu.ng/ ; https://wascal.futa.edu.ng/cms//uploads/Docs_1696492139.pdf |
| FUTAspace repository front page and community list | **read** (public, no login). A DSpace XMLUI site; communities are Schools, then Departments, then "Master's/Ph.D Thesis", plus a "Past Questions" community with a general-studies and per-school collections. School names and groupings **differ between community entries** (the list carries both older and newer school arrangements: several schools appear under more than one name or grouping). Item pages and metadata fields were not opened; theses were not harvested | http://futaspace.futa.edu.ng:8080/xmlui/ ; http://futaspace.futa.edu.ng:8080/xmlui/community-list |

### 5.1 What this means for "BCCMAS"

1. The term has **no public source** that this search could find. Treat it as **reported-by-user** until a FUTA-authorised person says what it stands for and supplies the document.
2. A hypothesis, not a finding: the handbook file is titled "Modified Curriculum", the programme is five years and 168 units where CCMAS Computing is four years and 120. A FUTA-modified five-year extension of CCMAS is consistent with what the user reports. If "BCCMAS" names that (for example a B.Tech variant), the user should say so; the model must not guess the expansion.
3. The handbook's 300 level second-semester codes appear to coincide with the NUC Data Science list, so a rule of "level 300 and above is BCCMAS" would mislabel rows that are CCMAS-derived. **Provenance must be stored per curriculum row, with a per-level-band default only as a convenience for the reviewer.**
4. The model therefore carries a `framework` and a `framework_verification` on **every curriculum row and on every curriculum version**, and a `level_band_framework` table of user-reported defaults that import tooling may use to pre-fill, never to publish.

## 6. Which combinations the handbook cannot answer

Detailed matrix in the design document §11. Summary:

* **Prerequisites:** none are listed. Cannot answer.
* **Elective choice rules:** none. Cannot answer.
* **Which admission cohorts the tables apply to:** only a cover window. Cannot answer.
* **Any curriculum version other than the current one:** none. Cannot answer how a 2023 entrant's list differs.
* **Direct Entry level 200 table:** the handbook has one set of tables for both routes; whether Direct Entry students take any rows differently (beyond skipping 100 level) cannot be answered.
* **300 level second semester, 400 level first semester, 500 level second semester:** extraction cannot reconstruct rows reliably.
* **Elective status (compulsory vs optional) and the meaning of `R`:** not in the tables.
* **Course owner when the prefix is shared:** not stated.

## 7. What the extraction gets right (and can seed)

* Level and semester headings for seven of ten tables.
* The existence of one table per level and semester, and the C/R/E column.
* Programme-level rules (durations, graduation minimums, CGPA, probation, load) are plain statements and can be checked quickly by a person.
* Section 8 headings give a second, independent pass at code, title and unit; **agreement between the two sections is a useful confidence signal** (see data plan §4).

## 8. Recommendations from this analysis

1. Treat the handbook as a *candidate* source only; no handbook row is published without a human verification record (data plan).
2. Ask the user to identify the real expansion and source document of "BCCMAS" before any band-to-framework mapping is marked verified.
3. Ask a FUTA-authorised academic representative for the printed pages of the three unreadable tables and for the 300 level second-semester total.
4. Do not commit the handbook, its text, or any FUTA course data (codes, titles, units) to this repository. The rights decision is in the data plan.
