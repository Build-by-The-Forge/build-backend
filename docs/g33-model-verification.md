# G-33 model verification table (DRAFT)

**Accessed:** 2026-11-20, from each provider's own pages (URLs below). **Status: draft; it enables no model.** "Verified" means the provider's own page states it. Anything resting on a model-extracted summary is marked. Prices are USD per 1M tokens.

## Gemini

Source: https://aistudio.google.com/docs/models/gemini-3.8-flash ("Latest update: September 2026"), https://aistudio.google.com/docs/pricing (price changes dated 2026-12-01 and 2027-01-01).

| Field | `gemini-3.8-flash` | Verified? |
|---|---|---|
| Listed | Yes, with model code `gemini-3.8-flash` | **Verified** (the pricing page's own text; one summary of it said "not listed" and was wrong) |
| Status | Stable | **Verified** |
| Context | 1,048,576 input, 65,536 output | **Verified** |
| Inputs | Text, image, video, audio, PDF; text output | **Verified** |
| Structured output | Supported | **Verified** |
| Function calling | Supported | **Verified** |
| Price, Paid Standard | $0.75 in / $3.75 out (incl. thinking) / $0.075 cached, through 2026-12-31; $1.50 / $7.50 / $0.15 from 2027-01-01; cache storage $0.50 per 1M per hour, then $1.00 | **Verified**, but the pricing page was only partly read |
| Price, Free tier | Free of charge; **used to improve products** | **Verified** |
| Batch | $0.375 / $1.875 then $0.75 / $3.75 | **Verified** |
| Search grounding | 5,000 free requests a month, then $14 per 1,000 | **Verified** |
| Serving | Hosted API; availability in Nigeria listed | **Verified** (availability, not data location) |
| Licence | Not applicable (hosted) | n/a |

Also listed: `gemini-3.6-flash` (Stable, same price through 2026-12-31), `gemini-3-flash-preview` (Preview; price from a summary, **unverified**). `gemini-3.7-flash` appears only in a docs index, **not found** on the models or pricing pages. Requests to `gemini-2.5-pro` route to `gemini-3.8-flash` on 2026-12-01.

**Report claim** (Notion) "$0.75 / $3.75, then $1.50 / $7.50": **matches** the page.

## Fireworks

Sources: https://fireworks.ai/pricing, https://docs.fireworks.ai/serverless/pricing.md, and each model page. Prices are input / cached input / output, Standard.

| Field | Nemotron 3.5 Lightning 30B A3B | gpt-oss-120b | DeepSeek V4.1 Flash |
|---|---|---|---|
| ID the report gave | `accounts/fireworks/models/nvidia-nemotron-3.5-lightning` | `accounts/fireworks/models/gpt-oss-120b` | `accounts/fireworks/models/deepseek-v4p1-flash` |
| ID found | **The report's ID was NOT FOUND.** The model exists as `accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b` (https://fireworks.ai/models/fireworks/nemotron-lightning-3p5-30b-a3b) | Found (https://fireworks.ai/models/fireworks/gpt-oss-120b) | Found (https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash) |
| Serving mode | Serverless supported; on-demand also | **Conflict:** the model page says "Serverless: Not Supported" (on-demand only); the pricing pages list it as serverless | Serverless supported; on-demand also |
| Price | $0.05 / $0.01 / $0.20 (matches the report) | $0.15 / $0.015 / $0.60 (matches) | $0.30 / $0.006 / $1.20 (matches); US-only router $0.45 / $0.009 / $1.80 |
| Context | 262,144 | 131,072 (FAQ says 128K) | 1,048,576 (page spec shows 1040k) |
| Structured output | Not stated per model (a generic page exists) | Not clearly stated ("Harmony-format structured outputs") | Not stated per model |
| Tool or function calling | Supported | Supported | Supported |
| Licence | Not stated on the Fireworks page (Hugging Face repo `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16`). **Report said "OpenMDW 1.1": unverified** | Apache 2.0 (model page FAQ); matches the report | MIT (model page FAQ); matches the report |
| Other | No image input; fine-tuning not supported. Created 7 Aug 2026 | Fine-tuning: FAQ says yes, spec table says no | Image input supported. Created 10 Sep 2026. Fine-tuning: spec says yes, a FAQ says no |

**Base URL** https://api.fireworks.ai/inference/v1 with an OpenAI-compatible client: **verified** in Fireworks' SDK examples. US-only: https://us.api.fireworks.ai/inference/v1.

**Not checked:** the report's "backups" (GLM 5.3 Flash, MiniMax M3); the report's latency claims. Spot prices appear on the pricing page for select models only.

## What the table does not show

- It does not show quality, latency or cost for BUILD's tasks. That is the 100-task evaluation (plan phase 3).
- It does not approve a model. Approval needs the provider's G-33 record approved first.
- Prices change: Gemini's already change on 2027-01-01. Re-check on the day any budget is set.

## Role hypotheses for the three Fireworks models (2026-11-20)

The user confirmed the three models as the intended portfolio. **No role is assigned.** Two sources suggest roles, and they differ:

| Model | Source A: the user's suggestion | Source B: the Notion report (unverified) | Decided by benchmark |
|---|---|---|---|
| Nemotron 3.5 Lightning 30B A3B | Agentic reasoning and multi-step work | Small-task execution, simple RAG, routing, summaries; "not for hard multi-step planning" | **No. Unassigned** |
| gpt-oss-120B | Complex reasoning and synthesis | Default orchestration | **No. Unassigned** |
| DeepSeek V4.1 Flash | High-volume multi-step work | Long-context work over 131K | **No. Unassigned** |

The sources contradict each other on Nemotron. Each model is evaluated against BUILD's agentic task suite, and for grounding, citation accuracy and abstention, before a role is assigned. A role also needs the structured-output status above, which Fireworks' pages don't state per model.
