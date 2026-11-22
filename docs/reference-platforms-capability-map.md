# Reference platforms and BUILD's capability map (DRAFT)

**Status: draft for the user and the reviewer. Documentation only.** It authorises no code, route, provider work or release change. **R1 does not change:** R1 stays the online core journey with a naive-RAG grounded tutor. Anything agentic is R2 and Pro. Provider work stays paused (user decision, 2026-11-21).

**Purpose.** The user wants BUILD to connect the strong ideas in today's learning products into one agentic educational platform for FUTA students. This document studies a set of reference platforms, says what is worth learning from each, maps each idea to a BUILD component, and ranks what to build first. It does not copy any product.

## 1. Method and sources

### 1.1 Rules

1. **Authoritative public sources only:** each platform's own site, help centre, official blog and published papers. Third-party reviews are used only when labelled as such, and none was needed for the claims below.
2. **Every claim names its source URL and the date it was read** (2026-11-22). Each platform section ends with what could not be read.
3. **Own words.** Nothing is quoted beyond a few words. No text, interface design, brand asset or content is reproduced. Capabilities and design ideas are fair to learn from; copying products is not, and BUILD builds its own.
4. **Vendor claims are not findings.** A marketing page that says a product is accurate is recorded as "claimed". Where a page states a limitation, that is recorded as the vendor's own admission.
5. **UNVERIFIED** means the official pages read didn't say it, or couldn't be read. It is not a negative finding.
6. **Repository claims are checked in code** at `build-backend` `e9067ed` and `ai-service` `4150c5f` and cite paths. Everything else about BUILD is a proposal.

### 1.2 Who read what

Each platform's pages were read by research agents using a page reader, and this document relied on their reports. Several official pages were blocked or returned no content; they are listed per platform. No platform's terms of service were read in full unless stated, so **nothing here is a legal reading of any product's terms.**

### 1.3 Platforms studied

| Group | Platforms | Read |
|---|---|---|
| Tutors | Khanmigo and Khan Academy | Partly: Khanmigo marketing and Khan Academy blog posts; help centre blocked |
| Source-grounded study | NotebookLM (now titled "Gemini Notebook" in Google's help pages) | Help-centre articles read |
| Photo-to-solution | Photomath; Socratic by Google | Photomath help and privacy read; **Socratic: no Socratic page readable** (the domain redirects to a Google Lens page) |
| Adaptive and memory | Knewton Alta, Anki, Duolingo, Brilliant | Alta vendor page; Anki manual; Duolingo research index (paper body unreadable); Brilliant help and blog |
| Not read | **Quizlet** (help pages refused access) | Nothing verified |
| Computation and search | Wolfram|Alpha, Perplexity | Official pages read |
| Assessment and workspace | Gradescope, Notion AI | Vendor pages read; Gradescope help refused access |
| African context | Kolibri, Ubongo | Official pages read; uLesson loaded only a title; Eneza Education's domain did not resolve |

**Suggested further platforms** (not yet studied, listed so the user can choose): Course Hero or Chegg-style study help (integrity risks are as instructive as the features), Coursera and edX (course structure and peer assessment), Desmos and GeoGebra (interactive maths), Mathway and Symbolab (symbolic solving), Elicit and Consensus (cited research search), Seneca and Revision apps (exam-board revision), Gradely, M-Shule and uLesson (African exam-prep), and exam-preparation apps for Nigerian national examinations (to be identified with students).

## 2. Platform teardown

For each platform: what makes it strong, how it works at a high level, known weaknesses, guardrails, audience, and what could not be verified. "Claimed" marks a vendor statement.

### 2.1 Khanmigo and Khan Academy

Sources (all read 2026-11-22): https://www.khanmigo.ai/ , https://www.khanmigo.ai/learners , https://www.khanmigo.ai/parents , https://blog.khanacademy.org/aiguidelines/ (2025-04-03), https://blog.khanacademy.org/khanmigos-first-chapter-changed-how-i-think-about-ai-a-note-from-sal-khan/ (2026-07-15, updated 2026-08-27), https://blog.khanacademy.org/edtech-can-work-decision-makers-have-to-check-the-evidence-first/ (2026-10-20), https://blog.khanacademy.org/four-stars-for-khanmigo-common-sense-media-rates-ai-tools-for-learning/ .

- **Strong because:** the tutor sits inside the exercises, videos and articles, so it sees the problem the student is on; teachers get planning and rubric tools and summaries of recent student work; teacher practice questions are generated and reviewed by the teacher before assigning (claimed).
- **How it works:** it guides with questions and asks students to explain their reasoning rather than handing over answers (claimed; the learner FAQ says it never gives the answer, which is a marketing statement, not a test result). The wider platform is mastery-based practice with teacher views of who is stuck.
- **Weaknesses (the vendor's own words):** AI can make errors in maths; the first version did not change learning as much as hoped; generating standards-aligned content on the fly is weak. A Common Sense review noted maths limits and occasional stereotype reinforcement. Khan Academy cites an independent study with small effects (0.06 to 0.08 of a standard deviation); the study itself was not read.
- **Guardrails:** under-18s need a parent or guardian to add them; parents see chat history and moderation alerts; teachers see their students' chats; moderation flags inappropriate use and emails an adult.
- **Audience:** elementary to college; paid for parents and learners (US billing address required), free for educators in listed countries.
- **Unverified:** current usage limits, exam-specific features, the country list, the districts price. Khan Academy's about, teachers and help-centre pages were blocked.

### 2.2 NotebookLM (Google; titled "Gemini Notebook" in its help centre)

Sources (read 2026-11-22): https://support.google.com/gemininotebook/answer/16164461 , https://support.google.com/gemininotebook/answer/16215270 , https://support.google.com/gemininotebook/answer/16213268 , https://support.google.com/gemininotebook/answer/17004255 .

- **Strong because:** answers are grounded in the user's own uploaded sources with inline citations, and the same sources become study guides, audio overviews, mind maps, flashcards, quizzes, slides and reports.
- **How it works:** retrieve the most relevant passages from the sources first, then write from them.
- **Weaknesses:** answers are meant to come from sources, but vague questions retrieve poorly; sensitive content can trigger safety flags; per-source and per-notebook caps apply; paywalled pages aren't imported and only page text is read.
- **Guardrails:** stricter content policy for under-18s and some features 18+ only; consumer uploads aren't used to train foundation models unless feedback is sent (feedback may be human-reviewed and kept up to three years); Education and Workspace uploads aren't human-reviewed or used for training; users are told not to upload what they have no rights to.
- **Audience:** browser users above the age of consent, Workspace for Education users of all ages; a free tier and paid tiers.
- **Unverified:** prices, maths-specific behaviour, handwriting, the rename beyond these pages.

### 2.3 Photomath and Socratic by Google

Sources (read 2026-11-22): https://photomath.com/ , https://support.google.com/photomath/answer/14330572 , /14333327 , /14328427 , /14334647 , /14332812 , /14327895 , https://photomath.com/privacy/ (effective 31 Oct 2023).

- **Photomath strong because:** camera scanning of printed or handwritten problems, step-by-step solutions with more than one method where available, an on-screen maths keyboard as an alternative, and editing of a scanned problem; the paid tier adds animated tutorials and deeper explanations.
- **How it works:** recognise the expression, then solve; if nothing appears in a couple of seconds the problem is unsupported or unrecognised.
- **Weaknesses:** a documented list of unsupported areas (for example statistics and probability, two-variable inequalities, interest, trigonometric inequalities); the high-school curriculum is not fully covered (its own FAQ); wrong or missing steps are reported by feedback. Accuracy is a company claim. The privacy policy says camera images improve the service and affiliates' machine-vision technology, and it both says images aren't shared with service providers and allows disclosure to machine-vision partners, a tension worth noting.
- **Guardrails:** framed as a way to understand methods and check answers (the FAQ cites a company figure that most students use it to check answers); consent required under 16.
- **Audience:** elementary to college; free basic tier, paid Plus.
- **Socratic by Google:** **no Socratic page could be read.** The socratic.org address redirects to a Google Lens page that describes step-by-step homework help and does not mention Socratic. Whether Socratic has been folded into Lens is unverified, so **nothing is claimed about Socratic.** Socratic-style behaviour is therefore studied through Khanmigo instead.

### 2.4 Knewton Alta

Source (read 2026-11-22): https://www.wiley.com/en-gb/learning/teaching-resources/courseware/knewton-alta .

- **Strong because (claimed):** continuous diagnosis of proficiency from each interaction, remediation that reaches back to prerequisite concepts, instruction organised by learning objective, per-question feedback, instructor dashboards.
- **How it works:** the page doesn't describe the mastery model, the graph structure or thresholds: **unverified.**
- **Weaknesses:** none stated; the only outcome evidence on the page is testimonials; independent efficacy unverified.
- **Guardrails:** instructor control of content; an accessibility effort (claimed). Privacy terms weren't read.
- **Audience:** instructors and students in listed courses (maths, sciences, economics, psychology, statistics); a per-semester or monthly price.
- **Deterministic or model-generated:** not stated.

### 2.5 Anki

Sources (read 2026-11-22): https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm.md , https://docs.ankiweb.net/faqs/frequently-asked-questions-about-fsrs.md .

- **Strong because:** open-source spaced repetition with two schedulers. The older variant multiplies intervals by an ease factor; FSRS models retrievability, stability and difficulty per user and is fitted to each user's review history, and Anki says it needs fewer reviews for the same retention.
- **How it works:** scheduling is deterministic given parameters; FSRS parameter fitting is machine learning over review history. It uses grades and intervals, not time spent.
- **Weaknesses:** Anki calls its comparisons with other models preliminary; FSRS gives longer first intervals and is more conservative on mature cards.
- **Guardrails and audience:** none stated; self-directed learners.
- **Unverified:** the deck-options manual wasn't read.

### 2.6 Duolingo

Sources (read 2026-11-22): https://research.duolingo.com/ , https://aclanthology.org/P16-1174/ (Settles and Meeder, 2016, metadata only).

- **Strong because:** a published research programme and a named spaced-repetition method, half-life regression, trained on a very large set of user-word pairs.
- **How it works:** a statistical model of memory decay drives review timing. The paper's body could not be extracted, so its features and results are **unverified**, and the pages read didn't describe its difficulty modelling.
- **Weaknesses, guardrails, whether features are model-generated:** unverified.

### 2.7 Brilliant

Sources (read 2026-11-22): https://brilliant.org/help/features/how-do-i-use-interactives-on-brilliant/ , https://brilliant.org/help/features/how-does-koji-work/ , https://blog.brilliant.org/hand-crafted-machine-made/ (2025-01-30).

- **Strong because:** interactive problems (typing expressions, dragging, manipulating objects) built from code; a tutor that can see the learner's entries and builds a plan.
- **How it works:** the tutor is built partly on a third-party model with Brilliant-specific behaviour; AI helps author problem variants with several rounds of human review, and Brilliant says AI cannot yet meet its bar for designing levels.
- **Weaknesses:** the claim that it rarely makes maths mistakes is self-reported with no metric; coverage is "most topics", with a limited free preview.
- **Guardrails:** stays on topic, safety filters, live alerts, a children's-privacy certification, and zero-retention terms with chat and audio processors (claimed).
- **Audience:** children to adults.
- **Unverified:** whether answer-checking is deterministic.

### 2.8 Quizlet

**Nothing verified.** Its help pages refused access and no other official page was read. Quizlet stays in the list because flashcard and study-mode design is directly relevant, but no claim is made about it.

### 2.9 Wolfram|Alpha

Sources (read 2026-11-22): https://www.wolframalpha.com/examples/pro-features/step-by-step-solutions , https://writings.stephenwolfram.com/2023/01/wolframalpha-as-the-way-to-bring-computational-knowledge-superpowers-to-chatgpt/ (2023-01-09), https://www.wolfram.com/resources/tools-for-AIs/ .

- **Strong because:** step-by-step solutions for hundreds of topics in maths, chemistry and physics (a paid feature), and a documented pattern of a language model calling a deterministic engine, then using the result.
- **How it works:** natural-language input is converted to Wolfram Language code and evaluated against curated data and algorithms; the vendor says answers carry the code and steps (claimed).
- **Weaknesses:** the "not hallucinations" statement is vendor marketing, with no independent evaluation found; Wolfram itself says many topics lack a formal computational form; API access is by request.
- **Guardrails, audience, offline use:** not stated on the pages read.
- **Why it matters here:** the clearest example of a deterministic tool grounding a model.

### 2.10 Perplexity

Sources (read 2026-11-22): https://www.perplexity.ai/help-center/en/articles/10352895-how-does-perplexity-work.md , https://www.perplexity.ai/help-center/en/articles/10354902-how-can-i-report-incorrect-or-inaccurate-answers.md .

- **Strong because:** every answer carries numbered citations to its sources; a multi-step research mode (claimed).
- **How it works:** interpret, search the web, summarise and cite.
- **Weaknesses:** the help pages don't claim each citation supports its sentence, which is **unverified**; users can report wrong or outdated answers.
- **Lesson:** a citation lets a reader check, but isn't proof of correctness. BUILD checks citations itself (section 3).

### 2.11 Gradescope

Source (read 2026-11-22): https://gradescope.com/ ; its help centre refused access.

- **Strong because:** rubric-based grading of paper, online and code work; for some question types it groups similar answers so an instructor can grade a group at once (claimed; institutional licence only); regrade requests are handled in the tool.
- **Guardrails:** the model is instructor review of groups and marks. AI accuracy and bias are **unverified**.
- **Lesson:** AI can cluster, but a human assigns the grade. That matches BUILD's rule that AI never assigns final grades.

### 2.12 Notion AI

Sources (read 2026-11-22): https://www.notion.com/help/notion-ai-faqs , https://www.notion.com/help/notion-ai-security-practices .

- **Strong because:** cited search across a workspace; pages are indexed as embeddings, retrieved, ranked, then used by the model; permissions are respected.
- **Guardrails:** customer data isn't used for training by default; retention terms differ by plan.
- **Audience:** teams. No offline use. No accuracy statement found.
- **Lesson:** retrieval that respects permissions is table stakes, and BUILD's read policy already does this.

### 2.13 African-context platforms

Sources (read 2026-11-22): https://learningequality.org/kolibri/ , https://www.ubongo.org/ , https://www.ubongo.org/shows/mobile-ivr/ .

- **Kolibri:** an open, free, offline-first platform. Content can be installed once and shared over a local network, USB or peer to peer; the Android app runs on older Android versions; quizzes give immediate feedback; no AI features described. Install and language-count figures are vendor claims.
- **Ubongo:** children's edutainment by TV, radio and mobile, including phone-call (IVR) services through operators in several African countries, including Nigeria, and a low-data WhatsApp service for ages 0 to 14. No per-call price found.
- **Lessons:** offline-first design and low-data delivery are normal in this setting and are not extras; BUILD's offline packs should be judged against Kolibri's sharing model. Both products target different ages from FUTA students.
- **Not read:** uLesson (a title only) and Eneza Education (the domain did not resolve). **No fourth African platform was verified.**

## 3. The BUILD mapping

### 3.1 What exists today (checked in code)

`build-backend` at `e9067ed`; `ai-service` at `4150c5f`.

| Component | What is there | Where |
|---|---|---|
| Source-grounded answers | Passages are retrieved, numbered and given to the model; an answer is grounded only if it cites a retrieved passage and cites nothing else, otherwise it is `NOT_COVERED`. Citations are built from stored chunk metadata | `ai-service` `app/services/rag/evidence.py` (`check_grounded`), `retrieval.py`, `recorder.py` |
| Provenance and permissions | The backend checks every source an answer used against current read permissions and withholds the whole answer on a failure | `build-backend` provenance check (#100); `app/api/ai.py` |
| Bounded tool registry and agent loop | Typed tools with schema, permission, timeout and budget; a loop with hard ceilings. **Built, not exposed on any route.** Three tools registered: `content.search`, `curriculum.lookup`, `draft.question` | `ai-service` `app/core/tools/`, `app/services/agents/executor.py`, `app/services/tools/builtins/` |
| Deterministic scoring | Attempts, scoring and result release are backend-authoritative | `build-backend` `app/application/assessment/attempt_handlers.py` |
| A deterministic mastery fold | `fold_mastery` folds a list of outcomes into a number with no model call. **Gated off:** Learning Memory is closed (`GATE_OPEN` is `False`) | `ai-service` `app/services/memory/memory_service.py`, `app/core/learning_memory_gate.py` |
| OCR | PaddleOCR and OpenVINO, PDF and image parsers, used by the ingestion pipeline for documents. **No route accepts a photo of a problem** | `ai-service` `app/services/ocr/` |
| CBT generation | A structured, grounded exam generator. **No route serves it** | `ai-service` `app/services/generation/cbt_exam.py` |
| Reading path | A path from a supplied root only | `ai-service` `app/api/v1/ai/read.py`, `app/services/tree/learning_path.py` |
| Catalogue and curriculum | Courses, topics, learning outcomes, reference materials, **course prerequisites**; CCMAS is a curriculum source | `build-backend` `app/domain/catalogue/{course,prerequisite,learning_outcome,reference_material}.py`, `app/domain/content/enums.py`, `docs/adr/008-curriculum-intelligence.md` |
| Offline | **Design only** | `docs/offline-content-pack-contract.md` (#122) |
| Agentic planner | **Design only** | `docs/study-planner-design.md` (#123) |
| Symbolic maths | **None found.** No symbolic-maths library or tool in `ai-service` | `git grep` of `requirements.txt`, `pyproject.toml` and `app/` |
| Spaced repetition and flashcards | **None found** in `ai-service` `app/` | `git grep` |
| Socratic mode and exam-mode refusal | **No code found** in `ai-service` `app/`. The exam-mode rule (AI off during official attempts, backend-enforced) is an adopted decision, not an implementation | `git grep` |
| Topic-level prerequisite graph | **Not verified.** Only course prerequisites were found | `app/domain/catalogue/prerequisite.py` |
| Past-question awareness | **A decision stands against it:** the contract has no examination-paper document type | `docs/milestone-register.md`, M3-D rulings |

### 3.2 Capability-to-component map

Releases: **R1** the online core (unchanged); **R2** offline, agentic, flashcards, personalisation; **Later** needs a decision first. "Gate" is the evidence required before shipping.

| # | Capability (inspired by) | BUILD component | Release | Exists today | Evidence gate |
|---|---|---|---|---|---|
| 1 | Answers from the student's own material, citations always (NotebookLM, Perplexity) | RAG and grounding | **R1** | Yes: `evidence.py`, backend provenance check | Grounded-answer rate, citation accuracy and abstention on **real FUTA material** (recall at 5 was 62.5% on real material per PRD §0.6), with confidence intervals |
| 2 | Permission-respecting retrieval (Notion AI) | The one read policy and `denied_assets` | **R1** | Yes | Boundary-gate runs; revocation tests |
| 3 | Course-code scope: "my MEE 201 notes" | Catalogue plus retrieval filter | **R1** | Catalogue yes; filter by course in retrieval unverified | Retrieval respects the course scope in tests |
| 4 | Study guides and summaries from sources (NotebookLM) | Grounded generation (naive RAG) | **R1** if the user wants it in the tutor; else R2 | An explain route exists (`app/api/v1/ai/explain.py`); a summary route was not found | Same bars as row 1; generated content labelled |
| 5 | Socratic mode: hint first, ask before telling (Khanmigo) | Tutor policy in the naive tutor; **exam-mode refusal enforced by the backend** | **R1 only if the user chooses; otherwise R2** | No code | A tutoring evaluation: hints don't leak answers on graded items; refusal tests during official attempts |
| 6 | Step-by-step symbolic maths as a registered tool (Photomath, Wolfram|Alpha) | Bounded tool registry plus a deterministic engine, provider-independent, runnable offline | **R2** | None | Step correctness against a test suite of FUTA course problems; the engine, not a model, decides correctness |
| 7 | Photo of a problem (Photomath) | OCR plus a maths-expression recogniser, feeding tool 6 | **R2** | Document OCR only | Recognition accuracy on handwritten and printed maths; camera-image privacy rules |
| 8 | Spaced repetition over flashcards made from the student's sources (Anki, Duolingo, Quizlet) | A deterministic scheduler plus grounded card generation | **R2** | None | Scheduler unit tests; retention evaluation; cards cite their source passage |
| 9 | Adaptive mastery over a prerequisite graph (Knewton Alta) | A deterministic mastery model over the catalogue, **the model only narrates** | **R2**, after the Learning Memory gate | `fold_mastery` (gated); course prerequisites | Calibration on real attempt data; the gate's conditions; AI never assigns mastery |
| 10 | Revision plans and multi-source research (Khanmigo teacher tools, Perplexity) | The bounded agentic planner | **R2, Pro** | Design only | The planner's evaluation bars |
| 11 | Offline-first delivery and sharing (Kolibri) | Offline content packs, lease and sync | **R2** | Design only | The contract's acceptance tests, on named real devices |
| 12 | Interactive practice with instant checking (Brilliant) | Practice generation plus a deterministic checker | **R2 or Later** | Generator unrouted | Checker correctness; labelled generated |
| 13 | Instructor review of clustered answers (Gradescope) | Lecturer workflows | **Later** (paused, PRD §0.5) | None | A separate decision |
| 14 | Low-data and voice delivery (Ubongo) | A messaging or voice channel | **Later** | None | A separate decision |
| 15 | Past-question awareness | Catalogue plus a document type | **Later** | **Blocked by an existing ruling** (no examination-paper document type) | The user and reviewer revisit the ruling, with the rights question for past papers |

### 3.3 Assessing the proposed FUTA STEM differentiators

These are assessed, not assumed.

- **A deterministic symbolic-maths engine as a registered tool (row 6).** Strong fit: Wolfram's own writing describes the pattern (a model calls an engine, the engine computes), and Photomath shows demand and also its limits (documented unsupported areas, accuracy only claimed). Provider-independent and offline-capable, so it survives the provider pause and serves poor connectivity. **Risks:** step-by-step *explanations* are harder than final answers; the engine must be tested against FUTA's real course problems; scope must be stated (what is unsupported). The correctness decision belongs to the engine, never to a model.
- **Photo-of-a-problem input (row 7).** The existing OCR is for documents, not handwritten maths. Treat as a separate recognition problem with its own accuracy measure. **Privacy risk:** Photomath's own policy shows how camera images can be reused; BUILD's rule should be that photos are not used to train anything and are deleted after use unless the student keeps them.
- **Socratic mode (row 5).** The pattern is well documented (Khanmigo), but its own authors say the first version did not change learning as much as hoped and that AI makes maths errors. It is cheap to build and needs a real evaluation. It must **refuse during official attempts**, enforced by the backend.
- **Source-grounded notebooks and study guides (rows 1 and 4).** BUILD's strongest foundation. NotebookLM shows the product shape; BUILD's checks are stricter (the citation rule and the backend provenance check).
- **Adaptive mastery over a prerequisite graph (row 9).** High value, but it depends on data BUILD doesn't yet have (attempt history at scale) and on a topic-level graph that isn't verified. Alta's pages don't describe their model, so there is nothing to copy; BUILD designs its own. **The mastery number is computed deterministically; the model only narrates it.**
- **Spaced repetition (row 8).** Anki documents two schedulers and FSRS's model of memory; Duolingo published half-life regression. A deterministic scheduler is low cost and works offline. Cards must be generated from the student's own sources, with the source cited.
- **Course-code and past-question awareness (rows 3 and 15).** Course scope is cheap and valuable. Past-question awareness collides with an existing ruling and a rights question, so it is a decision, not a build item.

## 4. Guard rails

1. **R1 does not change.** R1 stays the online core journey with a naive-RAG grounded tutor, online-only official CBT, and no document cache. Nothing in this map moves an item into R1 except where row 5 or 4 is marked as the user's choice.
2. **Anything agentic is R2 and Pro** (`docs/study-planner-design.md`).
3. **AI never assigns final grades or mastery.** Grades come from backend scoring; mastery comes from a deterministic model; the model may explain a number, never set it. Gradescope's design (AI groups, a human grades) points the same way.
4. **Academic integrity and exam mode.** No AI help during an official attempt, enforced by the backend, not the app. Socratic hinting must not leak graded answers. The risk that a tool becomes an answer service is real: Photomath's own FAQ cites that most students use it to check answers.
5. **Minors.** FUTA first-year students may be 16 or 17, and the age-eligibility question for Gemini is open. Khanmigo's model (a parent or guardian adds a minor, adults see chats) and Photomath's consent-under-16 rule are references, not decisions. Nothing here settles BUILD's policy.
6. **Copyright and rights of uploaded material.** Uploaded notes and past papers may belong to others. NotebookLM tells users not to upload what they have no rights to; BUILD's rights declarations are the student's assertions, not legal clearance, and nothing is shared beyond the student without publication consent.
7. **Privacy.** Camera images, chat logs and mastery data are personal data. Pseudonymous identifiers are still personal data.
8. **No copying.** BUILD borrows capabilities and design ideas stated in public documentation. It does not reproduce any product's text, screens, branding or content.
9. **No provider work resumes** because of this document. Gemini and Fireworks work stays paused (user, 2026-11-21); everything above is written to work with the paused state or without a provider (rows 6, 8 and 9 need none).

## 5. Roadmap (proposed; none of it is authorised)

**Now (documentation only, no provider work):** settle the decisions in section 7. Nothing is built from this document.

**R1 (unchanged scope):** the online core journey. The only items from this map that touch R1 are evidence work already planned: measure the grounded tutor on real FUTA material (rows 1 to 3) and decide whether Socratic hinting (row 5) and study guides (row 4) are R1 or R2.

**R2, in the order that costs least and needs no provider:**
1. **Deterministic maths tool (row 6).** Start with a design and a test suite built from real FUTA course problems, before any engine is chosen. It needs no provider and can be exercised offline. Gate: step correctness on that suite.
2. **Spaced repetition and flashcards (row 8).** A deterministic scheduler and cards generated from the student's sources, each citing its passage. Gate: scheduler tests and a retention evaluation.
3. **Offline packs (row 11)** per `docs/offline-content-pack-contract.md`, with device benchmarks.
4. **Socratic mode (row 5)** if not already in R1, with exam-mode refusal enforced by the backend.
5. **Adaptive mastery (row 9)**, after the Learning Memory gate is decided and enough attempt data exists to calibrate.
6. **The bounded agentic planner (row 10)**, Pro only, after the entitlement design is approved.
7. **Photo-of-a-problem input (row 7)**, after the maths tool exists to receive it, and after a recognition accuracy study.

**Later (each needs its own decision):** instructor tools (row 13), voice and low-data channels (row 14), past-question awareness (row 15, which first needs the existing ruling revisited), interactive practice (row 12).

## 6. Ranked recommendation: the top five capabilities

Ranked by impact on FUTA students against cost and risk. "Impact" is a judgement from the evidence above, not a measurement.

| Rank | Capability | Impact | Cost | Risk | Release | Why |
|---|---|---|---|---|---|---|
| 1 | **Answers from the student's own material, citations always** (rows 1 to 3) | Highest: it is the core of the product and is where BUILD is already strongest | Low: the grounding code and provenance check exist | Medium: retrieval quality on real material (62.5% recall at 5) is the open problem | R1 | Without it nothing else is trustworthy. The work left is quality, not construction |
| 2 | **Deterministic step-by-step maths tool** (row 6) | High for a STEM-heavy campus; the strongest differentiator and the clearest lesson from Wolfram and Photomath | Medium: an engine plus a tested step generator | Medium: step explanations are hard; scope must be honest | R2 | Provider-independent and offline-capable, so it survives the provider pause and poor connectivity |
| 3 | **Spaced repetition over source-cited flashcards** (row 8) | High for exam revision at low cost | Low: a scheduler is deterministic | Low | R2 | Fully deterministic, offline-friendly, and the evidence base (Anki, Duolingo's published method) is public |
| 4 | **Course-code and prerequisite-aware guidance** (rows 3 and 9, the non-gated part) | Medium to high: it makes answers and plans fit the student's courses | Low to medium: the catalogue and course prerequisites exist | Low, as long as mastery is not set by a model | R1 for scope, R2 for guidance | Uses data BUILD already owns |
| 5 | **Socratic tutoring with exam-mode refusal** (row 5) | Medium to high pedagogically | Low to build, medium to evaluate | Medium: leaking answers, and integrity | R1 only by the user's choice, else R2 | Khanmigo's own admissions show it needs evidence, not just a prompt |

Just outside the top five: **offline packs** (high impact for connectivity, but a larger build and heavily gated) and **photo-of-a-problem input** (high wow-factor, depends on the maths tool and a recognition study). **Adaptive mastery** matters but is gated by the memory gate and by data BUILD doesn't have yet.

## 7. Decisions the user must make

1. **Socratic mode and study guides: R1 or R2?** (This is the only place this map touches R1's scope; the default here is R2.)
2. **Is the symbolic-maths tool the first R2 build**, and which course problems form its test suite?
3. **Photo input:** accept the recognition study first, and decide the rule for storing or deleting camera images.
4. **Minors policy.** FUTA first-years may be 16 or 17. Decide the product policy (a guardian model, an 18+ gate for AI features, or something else); the Gemini age-eligibility question is open independently.
5. **Past questions.** Revisit the ruling that there is no examination-paper document type, and decide the rights position for past papers.
6. **Mastery data.** Decide when the Learning Memory gate is reviewed, because adaptive mastery waits on it.
7. **Quizlet and Socratic.** Decide whether to have them studied further through another route, since no official page could be read.
8. **Further platforms** from section 1.3's list worth studying, especially African exam-preparation apps to be named with students.
9. **Whether student interviews or a usage survey** should precede ranking, since "impact" here is a judgement and not data.

## 8. Recommendations

1. Treat row 1 as the real product work for R1: raise retrieval quality on real FUTA material before adding any new feature.
2. Start the maths-tool test suite now. It needs no provider, and a suite built from real FUTA problems is the main thing that makes the tool trustworthy.
3. Keep every number a student sees (a grade, a mastery score, a due date for review) deterministic and explainable, and let the model only narrate it.
4. Decide the minors policy before building anything that sends student data to a provider or stores camera images.
5. Get a real read of the platforms that blocked access (Quizlet, Socratic, parts of Khan Academy and Gradescope) through another route before relying on this map for them.
6. Talk to FUTA students before locking the ranking. A short study of how they actually revise would replace the judgement in section 6 with evidence.

## 9. The CCMAS requirement

**Requirement (the user's wording, 2026-11-22).** BUILD's Nigerian university academic catalogue and curriculum intelligence must use NUC CCMAS as its national academic benchmark, reconciled with institution-approved academic structures and session-specific departmental curricula. The system must preserve source provenance, curriculum versions and historical applicability. It must never assume that the national CCMAS document alone represents every university's complete approved curriculum.

**Acceptance criterion, stated first.** *A student's academic session must resolve to the correct historical curriculum version, not simply the latest curriculum for their department.* Every gap below is graded by whether it breaks this criterion.

### 9.1 Four reconciled layers

| Layer | What it holds | Authority |
|---|---|---|
| (a) NUC CCMAS | National programme benchmarks: core courses and learning outcomes. NUC treats it as a minimum framework (see 9.4 for what could be verified) | The national regulator |
| (b) University-approved academic records | Faculties or schools, departments, programme structures | The institution |
| (c) Departmental curriculum | Courses by level and semester, including institution-specific courses | The department, approved by the institution |
| (d) Academic session | The curriculum version actually applicable to a student's session | The institution's record for that session |

CCMAS is the benchmark, never the whole curriculum: layers (b) to (d) are the institution's, and BUILD must reconcile them rather than let the national document stand in for them.

### 9.2 Fields and behaviours that must be preserved

Institution and programme ids; department and faculty relationships; course code, title and credit units; level and semester; academic session; curriculum version and effective dates; whether a course is CCMAS core or institution-specific; source document, publication date and verification status. A curriculum change **never overwrites history**, and a student in one session must not silently inherit a newer curriculum. CBT question-bank classification, course selection, tutoring context and prerequisite mastery must resolve against the student's actual programme and curriculum **version**.

### 9.3 What was read

Design: `docs/adr/008-curriculum-intelligence.md` was read in the parts cited below, and the PRD §9.1 school list was read. `docs/architecture/academic-catalogue-specification.md`, `academic-knowledge-model.md`, `curriculum-intelligence.md` and PRD §10 to §12 were located but **not read in full in this pass**, so a row below can understate what they specify. Code: `app/domain/catalogue/`, `app/domain/curriculum/`, `app/domain/academic/profile.py`, `app/domain/tenant/academic_session.py`, `app/application/curriculum/` and the migrations named in each row. **This gap analysis does not implement or migrate anything.**

### 9.4 Gap table

"Breaks the criterion" means the gap would let a student's session resolve to the wrong curriculum version. Paths are in `build-backend` at `e9067ed`. "Closes in" names a **proposed** home, not a commitment: the register has no milestone for it yet.

| # | Required field or behaviour | Today | Evidence | Breaks the criterion? | Closes in (proposed) |
|---|---|---|---|---|---|
| 1 | Institution (tenant) and programme ids | **Exists** | `ProgrammeEntry` (`id`, `faculty_id`, `department_id`, `code`, `duration_years`) in `app/domain/catalogue/structure.py`; adoption holds `tenant_id`, `programme_id` in `app/domain/curriculum/adoption.py` | No | Done (M3-C, S-02) |
| 2 | Department and faculty relationships | **Exists** | `FacultyEntry`, `DepartmentEntry`, `ProgrammeEntry` in `structure.py` | No | Done |
| 3 | Course code, title, credit units, level, semester | **Exists** | `Course` in `app/domain/catalogue/course.py`; `BenchmarkCourse` (`code`, `title`, `credit_units`, `level`, `semester`) in `app/domain/curriculum/benchmark.py` | No | Done |
| 4 | Academic session | **Exists** | `AcademicSession` (`name`, `start_date`, `end_date`, `is_current`, `status`) in `app/domain/tenant/academic_session.py` | No | Done |
| 5 | Curriculum version and effective dates | **Partial** | `CurriculumVersion` has `effective_session_id` and `expires_session_id` (session-scoped, not dates) in `app/domain/catalogue/curriculum_version.py`; the benchmark has `benchmark_version` and a fingerprint in the adoption record. Dates come only through the session's `start_date` and `end_date` | **Yes**, if the session pointer is optional (row 9) | A design that fixes the version-to-session rule |
| 6 | CCMAS core versus institution-specific | **Partial** | `BenchmarkCourse.course_category` (default `"core"`) and `is_compulsory`; the effective-curriculum engine tags each course with an origin (`NATIONAL_BENCHMARK`, `INSTITUTIONAL_MODIFIED`, `INSTITUTIONAL_CUSTOM`) in `app/domain/curriculum/effective.py`. `course_category` is a free string, not a constrained value | No | A small catalogue design amendment |
| 7 | Source document, publication date, verification status | **Partial** | `CurriculumSource` and snapshots record `content_sha256` and a capture status (`app/domain/curriculum/source.py`); candidates are validated before activation (`docs/adr/008-curriculum-intelligence.md`). **No publication-date field was found** | No (provenance, not resolution) | A catalogue design amendment |
| 8 | **A student's profile bound to a session and a curriculum version** | **Missing** | The S-02 profile holds `programme`, `department`, `faculty`, `level` and `courses` only (`app/domain/academic/profile.py`); `app/application/academic/profile_service.py` references no session, adoption or benchmark | **Yes. This is the central gap** | An S-02 amendment design, then a migration |
| 9 | Resolve a session to the correct historical version | **Partial** | The resolution engine exists (`EffectiveCurriculumEngine.resolve` in `app/domain/curriculum/effective.py`) and the adoption record has `academic_session_id`, **nullable**. No query was found that selects an adoption by the student's session rather than the active one (`app/application/curriculum/effective_queries.py`) | **Yes** | The same S-02 amendment, plus a curriculum-intelligence design change |
| 10 | History is never overwritten | **Partial** | Design: superseded benchmark versions become immutable, and a student's record must reference the exact version active at the time (`docs/adr/008-curriculum-intelligence.md`, sections 3 and the version rules). Enforcement across the student-facing records was **not re-verified** | **Yes**, until rows 8 and 9 exist | Test evidence when the S-02 amendment lands |
| 11 | Course selection resolves against the student's version | **Missing** | Profile courses are validated against the catalogue, not against a version (`profile_service.py`; S-02 design) | **Yes** | The S-02 amendment |
| 12 | CBT question-bank classification against programme and version | **Missing** | No curriculum-version or adoption reference was found in the assessment domain; `curriculum_version_id` appears only in the catalogue (`app/domain/catalogue/curriculum_version.py`, migrations 0005 and 0019) | **Yes** | A follow-up to M3-E (assessment) after the S-02 amendment |
| 13 | Tutoring context and prerequisite mastery resolve to the student's version | **Missing** | `ai-service` has a `curriculum.lookup` tool (`app/services/tools/builtins/curriculum.py`) and a deterministic `fold_mastery` (`app/services/memory/memory_service.py`), neither carrying a version | **Yes** for R2 features | R2 designs (planner, mastery) |
| 14 | Reconciling the layers (national, institutional, departmental, session) | **Partial** | Institutional adoption with overrides over a national benchmark (`app/domain/curriculum/adoption.py`: `benchmark_curriculum_id`, `benchmark_version`, override types); a session-specific departmental curriculum is only indirectly supported through `academic_session_id` | **Yes**, for the session layer | The curriculum-intelligence design |
| 15 | Never treating CCMAS alone as the full curriculum | **Partial** | ADR 008 keeps `CurriculumVersion` (an institutional delivery package) apart from the national `BenchmarkCurriculum`, and the effective engine layers institutional content over the benchmark | No, if row 9 closes | Test: a student's effective curriculum includes institution-only courses |

**Reading the table.** Rows 1 to 4 are built. Rows 5, 6, 7, 10, 14 and 15 are partly built in the curriculum-intelligence code, which is strong. Rows 8, 9, 11, 12 and 13 are the break: the machinery that can resolve a historical version exists, but **nothing ties a student to it**, so today a student would resolve to whatever the catalogue serves, which is the latest. That is exactly the failure the acceptance criterion forbids.

**Minimum to meet the criterion** (a proposal, not a design): the S-02 profile records the academic session and the adoption (or version) it resolves against; every student-facing read of courses, topics, question banks and tutoring context takes that reference; a test shows a student in an earlier session keeps the earlier curriculum after a newer one is activated.

### 9.5 Cross-check against official sources (accessed 2026-11-22)

**FUTA's own website could not be read, so no discrepancy with PRD §9 can be reported.** `https://futa.edu.ng` answered HTTP 403, and the reader did not try variants or subdomains. Every statement in PRD §9.1 (the schools SOC, SAAT, SIMME and SET and their programmes, and the note that Architecture is not a SET programme) therefore remains **unverified against FUTA's published structure**, and this document **does not overwrite the PRD's lists**. A person with browser access to futa.edu.ng should compare the school, department and programme names and the course-code format, and report differences.

**NUC.** What was read:

| Page | Read | What it showed |
|---|---|---|
| https://nuc.edu.ng (home) | Yes | NUC lists among its functions laying down minimum academic standards and accrediting degrees, a general function and not a CCMAS definition |
| https://www.nuc.edu.ng/ccmas/ | Yes, no page date | A download list of 17 discipline documents (administration and management; allied health sciences; architecture; arts; basic medical sciences; computing; communication and media studies; education; environmental sciences; law; medicine and dentistry; pharmacy; sciences; social sciences; veterinary medicine; engineering and technology; agriculture). Uploads are dated March 2026 in their addresses; file names suggest 2022 and 2023 issue years, which are **hints, not verified issue dates** |
| https://nuc-ccmas.ng | **Not read** | NUC's page calls it the "new CCMAS"; it is on another host and is the likeliest place for the purpose text |
| The discipline documents | **Not downloaded or read** | They would hold the core and institution-specific split and implementation rules |

- **The 70 percent core and 30 percent institutional split is UNVERIFIED.** No figure appeared on any page read.
- **Whether CCMAS is described as a minimum framework**, its stated purpose and its implementation deadlines are likewise unverified on the pages read.
- **Programmes that matter here:** the `/ccmas/` page has "Computing", "Engineering/Technology", "Agriculture", "Environmental Sciences" and "Sciences" entries, which line up with the kinds of FUTA programmes in PRD §9.1. Whether each FUTA programme maps to a document, and which, is not checked.

**Next steps (proposals):** read https://nuc-ccmas.ng and the discipline documents that cover FUTA's programmes, record the core and institutional split and the issue year of each, and compare FUTA's own list in a browser. Nothing in the catalogue should be loaded from CCMAS until its source, version and verification status are recorded (row 7).
