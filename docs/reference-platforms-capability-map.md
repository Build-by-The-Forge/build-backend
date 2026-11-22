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
