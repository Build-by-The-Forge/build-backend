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
