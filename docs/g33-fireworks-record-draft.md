# G-33 record: Fireworks AI (DRAFT)

**Status: DRAFT. This approves nothing and adopts nothing.** Fireworks is *proposed and disabled*. It comes from a research report (Notion, 2026-11-18, https://app.notion.com/p/41c4e323b2f28052a699ebe18394fe6f) that is a proposal, not an approved record. This lane did not read that page; the review session summarised it. The report's claims below are marked **Report claim**, and each is checked or left unverified against Fireworks' own pages.

**Accessed:** 2026-11-20, by a research subagent through a page reader. Most Fireworks documentation pages show no date; where one does, it is given.

## 1. Sources read

| Source | Page's own date |
|---|---|
| Privacy policy, https://fireworks.ai/privacy-policy | "Last Modified: 16 SEP, 2026" |
| Zero Data Retention, https://docs.fireworks.ai/guides/security_compliance/data_handling | none |
| Data security and certifications, https://docs.fireworks.ai/guides/security_compliance/data_security.md | none |
| Pricing, https://fireworks.ai/pricing; serverless prices, https://docs.fireworks.ai/serverless/pricing.md | none |
| Serverless SLA FAQ, https://docs.fireworks.ai/faq-new/deployment-infrastructure/is-latency-guaranteed-for-serverless-models.md | none |
| Batch, https://docs.fireworks.ai/guides/batch-inference.md | none; shows "Batch is paused" |
| Account quotas, https://docs.fireworks.ai/guides/quotas_usage/account-quotas.md | none |
| Reserved throughput, https://docs.fireworks.ai/serverless/reserved-throughput.md | none |
| US-only serverless, https://docs.fireworks.ai/serverless/us-only-serverless.md | none; mentions pricing from 1 Sep 2026 |
| Model pages under https://fireworks.ai/models/ | none |

**Not read:**
- **Terms of Service.** https://fireworks.ai/terms-of-service answers HTTP 308 to a PDF on `cdn.sanity.io`, a host outside Fireworks' own domains. It was not followed.
- **Trust Center**, https://trust.fireworks.ai/, returned an empty shell.
- The data-residency page (https://docs.fireworks.ai/accounts/data-residency), the rate-limits page and the Secure Training page.

## 2. Training and retention

| Item | What the pages say |
|---|---|
| Training | Privacy policy: "No AI Training on Your Data"; prompts, training data and API inputs are not used to train or improve models "without your explicit opt-in" |
| **Report claim:** "zero data retention by default" | **Partly verified.** Fireworks "does not log or store prompt or generation data for open models, without explicit user opt-in"; data exists in volatile memory for the request. Metadata such as token counts is logged. With prompt caching, prompt data and KV caches can stay in volatile memory "for several minutes" |
| Exceptions | **Batch** (needs dataset storage; now paused). **Responses API** with `store=True`, which is the default: messages, responses and tool calls kept up to 30 days. `store=False` turns it off. Training workflows can persist datasets, checkpoints and traces |
| Scope | "Open models". Serverless versus dedicated isn't separated. Whether it covers every model BUILD would use is unconfirmed |
| Enterprise | Admins can enable a Zero Data Retention policy that rejects requests that would persist content |
| Inconsistency | Privacy policy 4.1 says "User Content … is stored and collected as part of the Service", not reconciled with the zero-retention page. It may refer to web-app content, **unconfirmed** |

## 3. Processing terms and security

| Item | Finding |
|---|---|
| DPA | **NOT FOUND** in any page read |
| Controller or processor | **NOT STATED.** The policy says Fireworks "may function as a service provider for other businesses" in certain situations |
| Safeguards | Standard Contractual Clauses cited for UK and EEA transfers; GDPR Local named as representative; controls "mapped to GDPR, CCPA" |
| Encryption | TLS 1.2+ in transit, AES-256 at rest; customer-data access is audit-logged |
| **Report claims:** SOC 2 Type II; ISO 27001, 27701, 42001; HIPAA with a BAA | **Stated by Fireworks' own pages** (SOC 2 Type II "certified"; the three ISO standards "Achieved"; HIPAA "compliant" on the data-security page, "with a BAA" on the pricing page). The certificates are said to be in the Trust Center, which was unreadable, so **the certificates themselves are unverified** |

## 4. Sub-processors and locations

| Item | Finding |
|---|---|
| Sub-processor list | **NOT FOUND.** The data-security page says sub-processors "undergo rigorous due diligence" and names none; the privacy policy lists categories only |
| Locations | Privacy policy: "servers for the Service in the US"; support and engineering may operate from the US. No default serverless inference region is stated |
| US-only option | `https://us.api.fireworks.ai/inference/v1` and `-us` router IDs, e.g. `accounts/fireworks/routers/deepseek-v4p1-flash-us` (priced $0.45 / $0.009 / $1.80). EU-only serverless: "contact sales"; no EU endpoint documented |
| **Report claim:** "prompts go to Fireworks, not DeepSeek, NVIDIA or OpenAI" | **Not stated either way.** Model pages show the model's origin ("Provider: DeepSeek") and say Fireworks serves it on its own stack. No page says prompts do or don't reach a vendor. **Unverified**; needs Fireworks' written answer |

## 5. Deletion

- Account deletion: personal information deleted "within 30 days" (policy, an aim).
- Active-workflow data: "permanently deleted with auditable confirmation", no timeline.
- Responses API: up to 30 days, or a DELETE call removes it at once.
- Batch: paused; stored datasets and outputs will be permanently deleted.
- Fine-tunes, uploaded datasets, logs: a Delete Dataset endpoint exists; **no timeline found**.

## 6. Availability and spend controls

| Item | Finding |
|---|---|
| **Report claim:** no published serverless SLA | **Verified:** serverless "does not currently come with" latency or availability SLAs |
| **Report claim:** 99.9% via Reserved Throughput | **Partly verified:** the pricing page says "99.9% uptime terms"; the reserved-throughput page gives no percentage; contact sales; overage has no SLA |
| **Report claim:** Batch 50% off | **Stale:** the pricing page says 50% off, but the Batch API page says "Batch is paused" and accepts no new jobs |
| **Report claim:** Spot 30% off | **Verified** for select models: best-effort, "throughput can drop to zero" |
| **Report claim:** monthly spend limit, auto-reload off | **Verified** for the limit: `firectl quota update monthly-spend-usd`; warning at 80%; at 100% all API requests pause. Auto Reload "never raises your limit"; no off-switch detail read |
| Rate limits | 10 RPM with no payment method; 6,000 RPM with a payment method and credits |

## 7. Models

See `docs/g33-model-verification.md`. In short: one of the report's three model IDs doesn't exist as written, and gpt-oss-120b's serverless status conflicts between two Fireworks pages.

## 8. Data protection BUILD must apply

Same as the Gemini record, and stated separately: no student names, school IDs or unnecessary identifying information; pseudonymous or opaque identifiers, not "anonymous"; a student's own question and passages can contain personal data that can't be stripped. Fireworks gives no DPA, no sub-processor list and no controller-processor statement in what was read, so contractual safeguards are **not established**.

## 9. Gaps that block an approval

1. No DPA and no controller or processor statement.
2. No sub-processor list; no statement about whether prompts reach model vendors.
3. Terms of Service unread; Trust Center unreadable.
4. US-hosted processing, with no documented African or EU region.
5. Zero retention covers "open models" and has named exceptions; the Responses API stores by default.
6. No serverless SLA; Batch is paused.
7. Model IDs and serving modes not all confirmed.

## 10. Decisions the user and the reviewer must make

1. **Whether to pursue Fireworks at all** for v1. Gemini is the approved first provider; this is a second provider for student passages and needs its own G-33 approval.
2. If yes, **ask Fireworks in writing** for: a DPA, the sub-processor list, whether prompts reach model vendors, the processing region for serverless, and the ZDR scope per model. Record the answers here.
3. **US-only endpoint** or the default one, given the unknown default region.
4. **Responses API:** forbid it for student material (use chat completions only, or `store=False`).
5. **Model set:** which of the verified models, if any, may receive passages.
6. **Free tier default.** The user's direction is that Free targets a low-cost Fireworks model once approved. That model must first clear a minimum grounded-answer, citation and abstention bar in evaluation; a small low-cost model citing correctly is unproven. Until then Free runs on Gemini under a strict budget.
7. **Key handling.** The API key is supplied separately by the user and is never committed, pasted into a document or logged; it lives in a secret manager or an environment file outside the repository. A key enables the integration process only and approves no production use.
8. **Cost urgency.** At the 2027 Gemini price a typical tutor answer (8,000 input and 500 output tokens) costs about $0.016; on the small Fireworks tier, at the page's unverified prices, about $0.0005 uncached or $0.0002 with input cached, roughly 30 to 80 times less. Governance and evaluation should start now, not only for R2.
9. **Spend:** set a monthly spend limit before any key is used. **Any account, key or paid call needs the user's explicit authorisation.** None exists.

**Prerequisites, not satisfied:** the above approval, a Fireworks account and key (a spending decision), and the Fireworks adapter, which doesn't exist and waits for ai-service #65. Until then Fireworks is not in `MODEL_PROVIDERS_APPROVED`, and no routing changes.

This document approves nothing, enables nothing, and authorises no spend.
