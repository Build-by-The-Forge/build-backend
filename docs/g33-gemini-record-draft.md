# G-33 record: Gemini API (DRAFT)

**Status: DRAFT. This approves nothing.** It records what Google's own pages say so the user and the reviewer can decide. `MODEL_PROVIDERS_APPROVED` stays empty and `GATE_OPEN` stays `False`.

**Gap:** G-33 in `contracts/mobile/gaps.yaml`: "Whether a model provider may train on retrieved passages hasn't been checked."

**Accessed:** 2026-11-20. **How:** each page was read by a research subagent through a page reader, and this lane relied on its report. Where the report says it worked from a model-extracted summary rather than the page's own text, the row below says so. Google's `ai.google.dev` pages now redirect to `aistudio.google.com/docs/...`; the pages carry no "last updated" line unless stated.

## 1. Sources

| Source | Page's own date |
|---|---|
| Gemini API Additional Terms, https://ai.google.dev/gemini-api/terms (redirects to https://aistudio.google.com/docs/terms) | "Effective March 23, 2026" |
| Abuse monitoring, https://aistudio.google.com/docs/usage-policies.md | none |
| Logs and datasets, https://aistudio.google.com/docs/logs-policy | none |
| Billing, https://aistudio.google.com/docs/billing | none; Prepay and Postpay "start taking effect March 23, 2026" |
| Pricing, https://aistudio.google.com/docs/pricing | none; price changes dated December 1, 2026 and January 1, 2027. Part read through a summary |
| Models and https://aistudio.google.com/docs/models/gemini-3.8-flash | "Latest update: September 2026" |
| Files, https://aistudio.google.com/docs/files.md; caching, https://aistudio.google.com/docs/caching.md | none |
| Available regions, https://aistudio.google.com/docs/available-regions.md | none |
| Cloud Data Processing Addendum, https://cloud.google.com/terms/data-processing-addendum | "Last modified: October 23, 2025" (from a summary) |
| Cloud Service Specific Terms, https://cloud.google.com/terms/service-terms | "Last modified April 2, 2026" (from a summary; the last ~4,100 characters unread) |
| Cloud subprocessors, https://cloud.google.com/terms/subprocessors | returned no readable content |
| `.../gemini-api/docs/zero-data-retention` | the target returns 404 |

**Not read, but cited by the terms:** the Google APIs Terms (https://developers.google.com/terms) and "Data Processing Addendum for Products Where Google is a Data Processor" (https://business.safety.google/processorterms/). The paid-tier guarantees below rest on that second document, so it must be read before approval.

## 2. Tiers

| | **Paid Services** (the "Standard" paid tier: calls through a Cloud project with an active billing account) | **Unpaid Services** (the free tier) | **Contributor tier** |
|---|---|---|---|
| Training or product improvement on prompts and outputs | **No.** Prompts (including system instructions, cached content, files) and responses are not used to improve products | **Yes.** Used to provide, improve and develop products and ML technologies | Yes, by design: invite-only private preview giving discounted prices in exchange for permission to use the project's data under the Unpaid terms |
| Human review | Only for abuse monitoring of flagged content (authorised Google employees) | Yes: reviewers may read, annotate and process inputs and outputs, after disconnection from account, API key and project | Same as Unpaid |
| Pricing page's own flag, "used to improve our products" | No | Yes | |
| Terms say | Processing under the DPA for products where Google is a processor | Don't submit sensitive, confidential or personal data | |
| Allowed in EEA, UK, Switzerland | Yes | Not as free use: only Paid Services may be used for API clients offered there | |

Both tiers sit under an 18-or-older rule: users must be 18 or older, and clients "must not be directed at, or likely to be accessed by" people under 18 (Additional Terms). **FUTA first-year students can be 16 or 17.** This is a decision point (section 8).

## 3. Retention

| Item | What the pages say |
|---|---|
| Abuse monitoring | Prompts, context and outputs retained **55 days** to detect policy violations (usage-policies page). The page doesn't split free from paid |
| Paid logging | "For a limited period of time", no number; may be stored transiently or cached in any country where Google or its agents have facilities (terms) |
| Developer logs (billing-enabled projects) | Not used for product improvement by default. Retention up to 55 days, settable to 7, 14, 28 or 55; then "marked for deletion". Logs **saved to datasets have no set period**, and shared datasets may be used to improve models and be human-reviewed. Logging is on by default for Interactions API calls and for `generateContent` in projects created on or after October 26, 2026 |
| Unpaid retention for product improvement | **NOT FOUND** |
| Zero data retention | **NOT FOUND.** The page doesn't exist and the docs index lists none |
| Files API | Stored 48 hours then deleted; 20 GB per project, 2 GB per file |
| Context caching | Implicit caching is on by default for Gemini 2.5 and newer. Explicit caching exists for supported Gemini 3 and 2.5 models on `generateContent`. Default TTL and deletion method: **NOT FOUND** |
| Grounding with Google Search or Maps | Prompts, context and output stored 30 days for grounded results and debugging |

## 4. Processing terms

- **Governing terms:** Gemini API Additional Terms (effective 2026-03-23) with the Google APIs Terms. For billing, the Cloud Terms sections on payment and miscellaneous provisions apply.
- **Roles:** for Paid Services Google is a processor for prompts and responses and a controller for account, billing and usage data (per the terms' own references). Unpaid terms state no role.
- **The Cloud DPA does not name the Gemini API** in what was read (summary). The Gemini API's paid-tier DPA is the separate processor-terms document, unread. Whether the Cloud DPA's deletion clock (180 days after an instruction, 30-day recovery) applies is **unconfirmed**.
- **Use limits:** professional or business use; no clinical use or medical advice.

## 5. Sub-processors and locations

| Item | Finding |
|---|---|
| Sub-processor list for the Gemini API | **NOT FOUND.** The Cloud subprocessors page returned no readable content |
| Where data is processed | Any country where Google or its sub-processors have facilities, subject to service-specific commitments (DPA, terms) |
| Data residency or regional control for the Gemini API | **NOT FOUND**, and no Nigeria or Africa data-location option |
| Availability in Nigeria | The regions page lists Nigeria among countries where the Gemini API is available. That is availability, not data location |

## 6. Deletion

| Data | Method and timeline |
|---|---|
| Files | `files.delete`, or automatic after 48 hours |
| Cached content | **NOT FOUND** |
| Tuned models | Deleting the model deletes its tuning content (Unpaid section; the Paid section doesn't say) |
| Logs | Marked for deletion after the chosen window; physical deletion timeline **NOT FOUND**; datasets must be deleted manually |
| Abuse-monitoring copies | 55 days |

## 7. Model and price facts (see `docs/g33-model-verification.md`)

`gemini-3.8-flash` is listed as **Stable**, with a 1,048,576-token input window and 65,536 output, structured outputs and function calling. Paid Standard price per 1M tokens: $0.75 input and $3.75 output through 2026-12-31, then $1.50 and $7.50. The free tier is free of charge and is the tier that trains.

## 8. Data protection BUILD must apply (both providers)

- No student names, school IDs or unnecessary identifying information in prompts. Where an identifier is needed it is pseudonymous or opaque, not "anonymous": pseudonymous data can still be personal data.
- A student's own question and course passages can contain personal data that can't be stripped. This record doesn't claim otherwise.
- Minimisation, identifier handling, retention, logging and contractual safeguards are stated per provider, here, and separately for Fireworks.

## 9. Gaps that block an approval on the evidence so far

1. The paid-tier processor terms (https://business.safety.google/processorterms/) were not read.
2. No Gemini API sub-processor list; no residency option for Nigerian students' data.
3. No unpaid retention figure and no zero-data-retention option.
4. Cache TTL and deletion method, and a log-deletion timeline, are missing.
5. The under-18 rule against FUTA's student population.
6. The Contributor tier's terms were seen only through the logs and pricing pages.

## 10. Decisions the user and the reviewer must make

1. **Approve or refuse Gemini Paid Services for student passages.** If approved, add `gemini` to `MODEL_PROVIDERS_APPROVED` only in an environment whose key is on a billing-enabled project.
2. **Never use the free tier or the Contributor tier for student or institutional material.** Free-tier keys stay for development and tests with non-student text only. Confirm.
3. **Under-18 students.** The terms bar clients likely to be accessed by under-18s. Decide: require 18+ at registration for AI features, get Google's written position, or accept the residual risk.
4. **Data location.** Accept processing in unspecified countries, or require a residency commitment before production.
5. **Logging.** Choose the project-log retention (7, 14, 28 or 55 days; recommend the shortest the team can operate with) and forbid saving logs to datasets.
6. **Caching.** Allow or forbid explicit caching of student passages until its TTL and deletion are documented.
7. **Read the processor terms** and record the result here before any approval.

**Prerequisite, not satisfied:** a **paid-tier key**, that is a Gemini API key on a Cloud project with an active billing account. None exists today, and creating one is a spending decision for the user. Until both the approval and the key exist, the Gemini adapter (ai-service #65) stays disabled for passages.

This document approves nothing, enables nothing, and authorises no spend.
