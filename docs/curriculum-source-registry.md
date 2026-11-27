# Curriculum source registry and coverage matrix (metadata only)

**Status: first checkpoint, for review.** Registry of sources and coverage for FUTA's schools, departments and programmes. **Metadata only: no scraped document, extracted text or real course data (codes, titles, units) is in this repository.** Originals, extracted text and manifests are in a private folder outside every repository. Companion documents: `docs/curriculum-handbook-analysis.md` (#134), `docs/curriculum-model-design.md` and `docs/curriculum-data-plan.md` (#136).

Access date for everything below: **2026-11-25** (some fetches ran past midnight).

## 0. Headline (read this first)

| Measure | Count | Meaning |
|---|---|---|
| Schools: distinct labels seen across all sources | 17 | Includes legacy and conflicting names (§4). Reconciled to **10 current candidate undergraduate groupings**, plus 2 reviewer-named schools (SOA, SSTE) with **no source found** |
| Departments / programmes **identified** | **61** | Union of the sources below. A department hosting several programmes cannot be told apart from the sources, so departments are counted as programmes |
| Of those, identified by the project's own PRD §9.1 | 27 | The PRD lists 4 schools; the rest come from third-party and FUTAspace lists |
| With **primary** FUTA curriculum evidence that is **usable** today | **0** | The only primary document is the Data Science handbook supplied by the user. It is private, extraction-grade, unverified and has no rights record |
| With primary evidence, unusable pending rights and verification | 1 | Data Science |
| With only handbook-like or secondary curriculum evidence | 0 | No other handbook or course outline was reachable |
| With **framework-only** evidence (NUC CCMAS lists a programme of that name) | 56 | **Not a course-level curriculum.** Never counted as one |
| Of those, ambiguous (one FUTA programme maps to two NUC programmes or documents) | 3 | Crop Soil and Pest; Food Science and Technology; Forestry and Wood Technology |
| No usable evidence of any kind (no NUC title match, or NUC document not retrieved) | 4 | Remote Sensing and GIS; Library Management Technology; Biomedical Technology; Medicine and Surgery |
| Framework assignment per programme and level band: **verified** | **0** | |
| Framework assignment: **reported-by-user** | 1 global claim | 100 to 200 level CCMAS, 300 to 500 level BCCMAS. **Applied to no programme automatically** |
| Framework assignment: **unknown** | 60 of 61 | Data Science is the one partial, unverified case (§6) |

**This registry can look more complete than it is: 61 programmes are identified; 0 have usable primary curriculum evidence.**

## 1. Three things kept separate

1. **Institutional coverage:** which schools, departments and programmes exist (§4, §5). Evidence: lists, not curricula.
2. **Document coverage:** which have verifiable CCMAS, BCCMAS, handbook or course-outline evidence (§3, §5 level columns).
3. **Framework applicability:** which framework applies to which programme and level band, with the evidence for that assignment (§6). Not inferred from 1 or 2.

## 2. Source treatment

| Source type | Treated as | Counted as |
|---|---|---|
| FUTA-published documents (handbooks, course outlines) | Primary institutional evidence | Course-level coverage, once rights and verification are done |
| NUC CCMAS / BMAS documents | Framework evidence | **Framework-only**; never a course-level FUTA curriculum |
| JAMB brochure | Programme identification and admission evidence | Identification (no first-party brochure was found, §3) |
| Other universities | Comparators only, labelled | Nothing for FUTA |
| User-reported 100-200 CCMAS / 300-500 BCCMAS mapping | Unverified claim | Nothing |
| Third-party list sites (legit.ng, schoolings.org, Wikipedia) | Secondary identification, low confidence | Identification only |
| FUTAspace community list (a FUTA repository) | Institutional structure evidence, undated | Identification only |
| Incomplete or ambiguous extraction (blank titles or statuses) | Low-confidence evidence | Unverified rows |
| Synthetic fixtures | Testing only | Nothing |

**Layering rule** (model detail in the design document): *source record* (original, immutable, hashed) then *extraction record* (machine output with confidence and flags) then *human correction record* (who, when, why; never overwrites) then *published curriculum row*. Four separate records. A correction never edits the extraction or the source.

## 3. Documents obtained and sources reached

Obtained. Originals, text and manifest are in the private folder; hashes are from its `manifest.tsv`:

| Source URL | Accessed | SHA-256 (first 16) | Size |
|---|---|---|---|
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Administration-and-Management.pdf | 2026-11-25 | `15402f6072dfd5a1…` | 4765 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Agriculture-2023.pdf | 2026-11-25 | `f0cf057835e3d47b…` | 3833 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Allied-Health-Sciences-2023.pdf | 2026-11-25 | `fa4dde6146e1d807…` | 5628 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Architecture-CCMAS-2023-FINAL.pdf | 2026-11-25 | `5c6513bbb1acf226…` | 1084 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Basic-Medical-Sciences-CCMAS-FINAL-December-26-2022.pdf | 2026-11-25 | `cd06202f7ed44e6c…` | 1254 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Computing-CCMAS-2023-FINAL.pdf | 2026-11-25 | `fb2eab5e4406afa0…` | 2224 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Engineering-Technology-CCMAS-2023-FINAL.pdf | 2026-11-25 | `99030f5f3c559324…` | 10146 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Environmental-Sciences-CCMAS-2023-FINAL.pdf | 2026-11-25 | `6640b2bb9d5b15b9…` | 3835 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Pharmacy-and-Pharmaceutical-Sciences-CCMAS-2023-FINAL.pdf | 2026-11-25 | `f3bb9251ed8f1c75…` | 1877 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Sciences-CCMAS-2023-FINAL.pdf | 2026-11-25 | `4276104a4a5f838e…` | 5690 KB |
| https://www.nuc.edu.ng/wp-content/uploads/2026/03/Social-Sciences-CCMAS-FINAL-2023-A.pdf | 2026-11-25 | `fdf440f6855a9c4a…` | 1965 KB |
| https://pgportal.futa.edu.ng/bin/AddendumtoPGAdvertfor2025-2026Session_%2027_June_2025.pdf | 2026-11-25 | `d1e21b1c075d0e3f…` | 190 KB |
| https://www.nuc.edu.ng/ccmas/ (discipline index page) | 2026-11-25 | `566dcbe8e9e120a0…` | 67 KB |

NUC `robots.txt` disallows only `/wp-admin/`. Six further NUC discipline documents exist and were **not retrieved**: Arts, Communication and Media Studies, Education, Law, Medicine and Dentistry, Veterinary Medicine. The Medicine and Dentistry document matters for FUTA's Medicine and Surgery row.

**Reached but not a curriculum.** `pgportal.futa.edu.ng`: the 2025/2026 postgraduate addendum (1 page; three postgraduate programmes; no curriculum). `futaspace.futa.edu.ng:8080` (a FUTA repository with no robots.txt): front page, community list and a title browse page, read in the in-app browser; **no item page and no thesis was opened**.

**Could not be read, and not bypassed:** `www.futa.edu.ng`, `soclibrary.futa.edu.ng`, the WASCAL PDF, and every school or department sub-site probed (`seet`, `sos`, `saat`, `svg`, `soc`, `set`, `sems`, `sps`, `sls`, `slit`, `sese`, `simme`, `shht`, `csc`, `sen`, `ifs`). Each returned HTTP 403 with a managed bot challenge, including in the in-app browser. That is an access control and nothing was done to get past it. Consequently **no FUTA-published curriculum, handbook, calendar, grading regulation or admission page could be collected.** No first-party JAMB brochure was found (search returned third-party mirrors only). `myschoolgist.com` returned 403.

Secondary pages read (identification only; read through a fetch tool, so no hashes):
* https://en.wikipedia.org/wiki/Federal_University_of_Technology_Akure (revision 1387330772);
* https://www.legit.ng/education/1619603-futa-courses-admission-requirements-federal-university-technology-akure (published 2024-10-21);
* https://schoolings.org/updated-list-of-courses-offered-in-federal-university-of-technology-akure-futa/ (undated; reader comments are not official).

## 4. Institutional spine: schools

| School label seen | Seen in | Notes |
|---|---|---|
| SOC Computing | PRD, FUTAspace, Wikipedia, Legit | Data Science (PRD, handbook) missing from FUTAspace, Wikipedia, Legit |
| SAAT Agriculture and Agricultural Technology | all | Nutrition and Dietetics only in PRD and Legit |
| SET Environmental Technology | PRD, FUTAspace, Wikipedia, Legit, Schoolings | PRD says Architecture is not SET; three sources put it there |
| SEMS Earth and Mineral Sciences | FUTAspace, Wikipedia, Legit, Schoolings | Surveying and Geoinformatics placement conflicts |
| SLS Life Sciences | FUTAspace, Wikipedia, Legit | Schoolings puts them under School of Sciences |
| SPS Physical Sciences | FUTAspace, Wikipedia, Legit | Spelled "Science" in Wikipedia |
| SLIT Logistics and Innovation Technology | FUTAspace, Wikipedia, Legit | Schoolings calls it School of Management Technology |
| SESE Electrical and Systems Engineering | FUTAspace, Wikipedia | Which departments sit here: unknown |
| SIMME Infrastructure, Minerals and Manufacturing Engineering | PRD, FUTAspace (empty), Wikipedia | PRD lists six departments; FUTAspace has none under it |
| SBMS / SCS / SBCS / SHHT / College of Health Sciences | FUTAspace, Wikipedia, Legit | Several names for a health grouping |
| SEET Engineering and Engineering Technology | FUTAspace (older), Legit, Schoolings | Probably the pre-split school |
| SOS Sciences, SOMTECH Management Technology | FUTAspace, Schoolings | Probably pre-split schools |
| SPGS Postgraduate | Wikipedia | Not an undergraduate school |
| SOA, SSTE | named by the reviewer | **No source found** |

## 5. Coverage matrix: programmes (61)

**Identified by:** P = PRD §9.1; R = FUTAspace community list; L = legit.ng; S = schoolings.org; W = Wikipedia; H = Data Science handbook (user-supplied, private); N = search snippet only.

**Level columns** (each programme, each level has its own status):
* `F` = framework only: a NUC document lists a programme of that name. The NUC Data Science tables were read; for the other programmes the per-level tables have **not** been individually checked;
* `?` = a fifth level may exist at FUTA; the duration at FUTA is not established (NUC lists engineering and architecture as five-year, marked `F`);
* `P*` = primary evidence exists privately: extraction-grade, unverified, rights pending, with parts unreadable (300 level semester 2, 400 level semester 1, 500 level semester 2);
* `-` = none found.

| School (as grouped) | Programme (as reported) | Identified by | NUC framework document / programme title | L100 | L200 | L300 | L400 | L500 | Note |
|---|---|---|---|---|---|---|---|---|---|
| SOC | Computer Science | P R L S | Computing: Computer Science | F | F | F | F | ? |  |
| SOC | Cyber Security | P R L | Computing: Cybersecurity | F | F | F | F | ? |  |
| SOC | Information Systems | P R L | Computing: Information Systems | F | F | F | F | ? |  |
| SOC | Information Technology | P R L | Computing: Information Technology | F | F | F | F | ? |  |
| SOC | Software Engineering | P R L | Computing: Software Engineering | F | F | F | F | ? |  |
| SOC | Data Science | P H | Computing: Data Science | P* | P* | P* | P* | P* | Handbook (user-supplied, private); absent from the FUTAspace list |
| SAAT | Agric Extension and Communication Tech | P R L S | Agriculture: Agricultural Extension | F | F | F | F | ? |  |
| SAAT | Agricultural and Resource Economics | P R L S | Agriculture: Agricultural Economics | F | F | F | F | ? |  |
| SAAT | Animal Production and Health | P R L S | Agriculture: Animal Science | F | F | F | F | ? |  |
| SAAT | Crop, Soil and Pest Management | P R L S | Agriculture: Crop Science / Soil Science (two NUC programmes) | F | F | F | F | ? | ambiguous match |
| SAAT | Ecotourism and Wildlife Management | P R L S | Agriculture: Forest Resources and Wildlife Management | F | F | F | F | ? |  |
| SAAT | Fisheries and Aquaculture Technology | P R L S | Agriculture: Fisheries and Aquaculture | F | F | F | F | ? |  |
| SAAT | Food Science and Technology | P R L S | Agriculture and Engineering-Technology: Food Science and Technology (in two NUC documents) | F | F | F | F | ? | ambiguous: two NUC documents |
| SAAT | Forestry and Wood Technology | P L S | Agriculture / Engineering-Technology: Forest Resources... / Wood Products Engineering | F | F | F | F | ? | ambiguous match |
| SAAT | Nutrition and Dietetics | P L | Allied-Health-Sciences: Human Nutrition and Dietetics | F | F | F | F | ? | in Allied Health document |
| Engineering (SESE or SIMME unresolved) | Agricultural Engineering | P R L S | Engineering-Technology: Agricultural and Biosystems Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Civil Engineering | P R L S | Engineering-Technology: Civil Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Industrial and Production Engineering | P L | Engineering-Technology: Industrial and Production Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Mechanical Engineering | P R L S | Engineering-Technology: Mechanical Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Mining Engineering | P R L S | Engineering-Technology: Mining Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Metallurgical and Materials Engineering | P R L S | Engineering-Technology: Materials and Metallurgical Engineering | F | F | F | F | F |  |
| Engineering (SESE or SIMME unresolved) | Electrical and Electronics Engineering | R L S | Engineering-Technology: Electrical and Electronic Engineering | F | F | F | F | F | not in PRD 9.1 |
| Engineering (SESE or SIMME unresolved) | Computer Engineering | R L | Engineering-Technology: Computer Engineering | F | F | F | F | F | not in PRD 9.1; conflicting reports |
| Engineering (SESE or SIMME unresolved) | Mechatronics Engineering | L | Engineering-Technology: Mechatronics Engineering | F | F | F | F | F | single source |
| Engineering (SESE or SIMME unresolved) | Chemical Engineering | L | Engineering-Technology: Chemical Engineering | F | F | F | F | F | single source |
| Engineering (SESE or SIMME unresolved) | Information and Communication Engineering | L | Engineering-Technology: Information and Communication Engineering | F | F | F | F | F | single source |
| SET | Building Technology | P R L S | Environmental-Sciences: Building | F | F | F | F | ? |  |
| SET | Estate Management | P R L S | Environmental-Sciences: Estate Management | F | F | F | F | ? |  |
| SET | Industrial Design | P R L S | Environmental-Sciences: Industrial Design | F | F | F | F | ? |  |
| SET | Quantity Surveying | P R L S | Environmental-Sciences: Quantity Surveying | F | F | F | F | ? |  |
| SET | Urban and Regional Planning | P R L S | Environmental-Sciences: Urban and Regional Planning | F | F | F | F | ? |  |
| SET | Surveying and Geoinformatics | P R L S | Environmental-Sciences: Surveying and Geoinformatics | F | F | F | F | ? | SEMS per one source |
| SET | Architecture | R L S | Architecture: Architecture | F | F | F | F | F | PRD 9.1 says NOT a SET programme: conflict |
| SEMS | Applied Geophysics | R L S W | Sciences: Applied Geophysics | F | F | F | F | ? |  |
| SEMS | Applied Geology | R L S | Sciences: Geology | F | F | F | F | ? |  |
| SEMS | Meteorology and Climate Science | R L S W | Sciences: Meteorology | F | F | F | F | ? |  |
| SEMS | Marine Science and Technology | R L S W | Sciences: Marine Science | F | F | F | F | ? |  |
| SEMS | Remote Sensing and GIS | R L S W | none found | - | - | - | - | - | no NUC title found |
| SLS | Biochemistry | R L S | Sciences: Biochemistry | F | F | F | F | ? |  |
| SLS | Biology | R L S | Sciences: Biology | F | F | F | F | ? |  |
| SLS | Biotechnology | R L | Sciences: Biotechnology | F | F | F | F | ? |  |
| SLS | Microbiology | R L S | Sciences: Microbiology | F | F | F | F | ? |  |
| SPS | Chemistry | R L S | Sciences: Chemistry | F | F | F | F | ? |  |
| SPS | Mathematical Sciences | R S | Sciences: Mathematics | F | F | F | F | ? |  |
| SPS | Physics | R L S | Sciences: Physics | F | F | F | F | ? |  |
| SPS | Statistics | R S | Sciences: Statistics | F | F | F | F | ? |  |
| SPS | Industrial Mathematics and Computer Technology | L | Sciences: Industrial Mathematics | F | F | F | F | ? | single source |
| SLIT | Project Management Technology | R L S | Administration-and-Management: Project Management | F | F | F | F | ? |  |
| SLIT | Transport Management Technology | R L S | Administration-and-Management: Transport Management | F | F | F | F | ? |  |
| SLIT | Entrepreneurship Management Technology | R L S | Administration-and-Management: Entrepreneurship | F | F | F | F | ? |  |
| SLIT | Accounting | L | Administration-and-Management: Accounting | F | F | F | F | ? | one source says not offered |
| SLIT | Business Information Technology | L | Administration-and-Management: Business Information Technology | F | F | F | F | ? | single source |
| SLIT | Economics | L | Social-Sciences: Economics | F | F | F | F | ? | single source |
| SLIT | Library Management Technology | S | none found | - | - | - | - | - | single source; no NUC title found |
| Health (SBMS / SHHT / CoHS) | Anatomy | R L | Basic-Medical-Sciences: Human Anatomy | F | F | F | F | ? |  |
| Health (SBMS / SHHT / CoHS) | Physiology | L | Basic-Medical-Sciences: Physiology | F | F | F | F | ? |  |
| Health (SBMS / SHHT / CoHS) | Medical Laboratory Science | L | Allied-Health-Sciences: Medical Laboratory Science | F | F | F | F | ? |  |
| Health (SBMS / SHHT / CoHS) | Public Health | R L | Allied-Health-Sciences: Public Health | F | F | F | F | ? |  |
| Health (SBMS / SHHT / CoHS) | Nursing Sciences | N | Allied-Health-Sciences: Nursing Science | F | F | F | F | ? | search snippet only; page not read |
| Health (SBMS / SHHT / CoHS) | Biomedical Technology | R L | none found | - | - | - | - | - | no NUC title found |
| Health (SBMS / SHHT / CoHS) | Medicine and Surgery | R L | none found | - | - | - | - | - | NUC Medicine and Dentistry document exists, not retrieved |

No cell in this matrix is course-level verified. `F` is not a course list for a FUTA student.

## 6. Framework applicability

| Question | Finding |
|---|---|
| What do the NUC CCMAS discipline documents cover? | Programmes **across levels**. The Data Science tables in the Computing document run through 400 level, and engineering and architecture are five-year. So the NUC documents are **not 100 to 200 level only**, which does not match the user-reported "CCMAS = 100-200" |
| Is there a public document for "BCCMAS"? | **No.** Not on the NUC index, the announcement, the discipline documents, or in searches |
| Can the user-reported band mapping be applied to any programme? | **No.** It is stored as one reported-by-user claim, applied to none |
| Does evidence exist for any programme-and-band assignment? | One partial case (Data Science): some 200 and 300 level rows coincide with the NUC list, and the handbook adds 400 and 500 level of its own. Unverified; row-level only |
| Verified assignments | 0 |

## 7. Conflicting or ambiguous source records

1. School count: Wikipedia "nine plus a College" (12 listed), Legit 13, Schoolings 7 (lists 6).
2. Engineering: one school (Legit, Schoolings) vs SESE plus SIMME (Wikipedia, FUTAspace); departments 6 (Schoolings) vs 11 (Legit); PRD lists six under SIMME.
3. Computing: no School of Computing in Schoolings; Computer Science sits under Sciences there.
4. Physical sciences: SPS vs SOS naming and membership; Industrial Mathematics only in Legit.
5. Life sciences: Biotechnology only in Legit and FUTAspace.
6. Surveying and Geoinformatics: SET (FUTAspace, Legit, Schoolings, PRD) vs SEMS (Wikipedia).
7. Architecture: not SET (PRD) vs SET (three sources).
8. Agriculture: Nutrition and Dietetics and Research Farm only in Legit; Forestry and Wood Technology has zero items in FUTAspace.
9. Management: Accounting and Economics only in Legit (a Schoolings comment says Accounting is not offered); Library Management Technology only in Schoolings; Transport vs Logistics naming.
10. Health: Medicine, Biomedical Technology, Physiology and Medical Laboratory Science only in Legit; Schoolings comments say medicine and biomedical technology are not offered.
11. Data Science: in PRD and the user's handbook, absent from FUTAspace, Wikipedia, Legit and Schoolings.
12. Duration: only an informal comment claims five years for some programmes; no official figure was reachable.
13. The handbook's own outline and synopsis disagree in places (analysis document §4.4).

## 8. Gaps, ranked (provisional)

No public enrolment figures were found. **The order below is provisional and not based on enrolment.** Method: (a) first-year common courses shared by many programmes come first, because one verified service-course record serves many students; (b) then schools by number of identified programmes; (c) replaced by **aggregate** enrolment or intake per programme as soon as the user or FUTA supplies it. Collection is never blocked on this order.

| Rank | Gap | Programmes affected |
|---|---|---|
| 1 | FUTA-published 100 and 200 level common courses (general studies, basic mathematics, physics, chemistry, biology, statistics, computing) used across schools | up to all 61 |
| 2 | No FUTA primary evidence for Engineering (SESE and SIMME); school structure itself unresolved | 11 |
| 3 | School of Agriculture | 9 |
| 4 | School of Environmental Technology (including the Architecture placement) | 7 |
| 5 | School of Logistics and Innovation Technology (programme list itself disputed) | 7 |
| 6 | Health grouping (offered programmes disputed; NUC Medicine document not retrieved) | 7 |
| 7 | School of Computing apart from Data Science | 5 |
| 8 | Sciences (SLS, SPS, SEMS) | 14 |
| 9 | Reviewer-named schools SOA and SSTE | unknown: no source |
| 10 | Data Science: unreadable tables, rights record, verification | 1 |

## 9. What a student could be offered today, per programme

| Evidence state | Programmes | What the app does |
|---|---|---|
| Evidence-backed and verified | 0 | n/a |
| Low-confidence primary (Data Science, private) | 1 | Not served until rights and verification; manual selection |
| Framework-only | 56 | Manual selection; the app says plainly that the department's list is not known; may show the framework programme title as context, never as the student's course list |
| Nothing | 4 | Manual selection |

The model carries a missing-evidence state per programme and level so the app can say what is unknown, and it supports a **partial curriculum** (some levels known, others not).

## 10. Rights question (decision for the user and reviewer)

Whether course lists published by the university may be used, with attribution and verification by an authorised FUTA representative, is unresolved. NUC documents are published for national use, but their reuse terms were not located and must be confirmed. FUTA documents need FUTA authorisation (G-34-style record). Until then this registry holds metadata only.

## 11. Data handling

* Private folder `C:\Users\midef\BUILD-data\curriculum-sources\`: one subfolder per source with the original, its `pdftotext` output, and a shared `manifest.tsv` (URL, folder, access date, SHA-256, size). Nothing from it is committed or uploaded as a CI artifact.
* Fetching: plain descriptive User-Agent, robots.txt checked first, about four seconds between requests, one process at a time, foreground, manifest written after each file.
* No BUILD or student data was sent to any site.

## 12. Recommendations

1. Ask FUTA (or the user, who may hold printed copies) for the **school and department list as published by the Registry** and **aggregate intake per programme**; both fix the spine and the priority order.
2. Ask a FUTA-authorised person for departmental handbooks in the order of §8, and for the meaning and document of "BCCMAS".
3. Retrieve the six remaining NUC documents, starting with Medicine and Dentistry.
4. Run the per-programme NUC table check so `F` cells become verified framework facts.
5. Decide the rights path (§10) before any FUTA document is loaded.
