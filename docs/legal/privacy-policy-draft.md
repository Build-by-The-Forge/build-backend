# BUILD Privacy Policy

> **DRAFT — NOT FOR PRODUCTION USE — requires legal review and approval by the appropriate adult and legal authority before publication.**
> This text is a working draft prepared from the product's design and code. It is **not legal advice**, has not been reviewed by a lawyer, and must not be shown to students as a binding or accurate notice. Everything in `[square brackets]` is a placeholder the responsible adult must supply or a point counsel must decide. Statements about the law are marked **UNVERIFIED** where the source could not be read (section 14).

**Version:** draft 0.1. **Effective date:** [EFFECTIVE DATE]. **Companion document:** `docs/legal/terms-of-service-draft.md`.

## 1. Who is responsible for your data

Two different things are named here on purpose, and they may be different parties:

- **Legal entity (the registered operator of BUILD):** [LEGAL ENTITY NAME AND REGISTRATION NUMBER, or a statement that BUILD is not yet a registered organisation. **No company name has been invented.**]
- **Data controller (the party that decides why and how your personal data is processed):** [DATA CONTROLLER, to be decided].
  - **Do not assume BUILD and a participating university have the same responsibilities.** Depending on how student data is collected and used, BUILD may be a controller, the university may be a controller, they may be joint controllers, or one may process data for the other. **These roles are open questions** and counsel must settle them; this notice must then state the answer plainly.
- **Data Protection Officer:** [NAME AND EMAIL, or a statement that none is required, as counsel decides].
- **Contact:** [CONTACT EMAIL AND ADDRESS].

## 2. What this notice covers

How BUILD handles personal data of students who use the BUILD app and service. It does not cover other websites or apps, or your institution's own systems.

## 3. What we collect

The list below comes from how BUILD is built. **It must be re-checked against the final product before publication.**

| Data | Why we hold it | Notes |
|---|---|---|
| **Account:** email address, name [confirm fields], a password stored only as a salted hash [counsel and engineering: confirm], your institution membership | To create and secure your account | A new registration waits in a holding table, with its password hash, until it is completed; engineering must confirm how long a failed one is kept |
| **Academic profile:** programme, department, faculty, level and enrolled courses | To show you your courses and give answers in the right context | |
| **Study material you upload:** the files, the text taken from them, their pieces and a numeric representation (embedding) used to search them, and what you tell us about who owns them | To store, scan and search your material and answer your questions | Files are scanned for malware before use. A file with no clean scan result is not processed |
| **Assessments:** your answers, attempts, scores and results | To run assessments and show results | Scores are computed by the system by fixed rules |
| **Your questions to the tutor and its answers** | To answer you | See section 7 on whether they are kept |
| **Device and usage records:** device platform and last-seen time, security and error logs, request identifiers | To keep the service secure and working | [Confirm what else, such as IP addresses, is logged] |

We do not intend to collect special categories of data (for example health, religion) and ask you not to put them in your questions or uploads. **You may, however, include personal data in your own questions and documents that we cannot detect or remove.**

## 4. Why we use it, and on what basis

[COUNSEL TO COMPLETE. For each purpose in section 3, state the lawful basis (for example consent, contract, legal obligation, legitimate interests) under the Nigeria Data Protection Act. **The list of bases in the Act was not read when this was drafted and is UNVERIFIED.**]

We use your data to run your account and your studies, keep the service secure, meet legal duties, and improve the service in ways [COUNSEL: scope]. **We do not sell your personal data. We do not use your uploaded material to train AI models.** [Counsel and engineering: confirm both statements against the final processing and any provider's terms.]

## 5. Under-18 users

**Placeholder for a policy the responsible adult and counsel must decide; not a statement of the law.**

- Some students may be under 18, and Nigerian law treats persons under 18 as children for many purposes. Data protection law may require a parent or guardian's involvement and special care with a child's data. **The exact age threshold, the consent rule, any age-verification duty and any education exception are UNVERIFIED** (section 14).
- [DECISION: the age policy, how age is confirmed, what is kept about it, and the guardian process.]
- For under-18 users BUILD will [SAFEGUARDS: no marketing, no profiling beyond study support, a plain-language notice, guardian contact route, limited features, shorter retention].
- **AI processing of any student's material by an outside provider is not happening (section 6), and will not start for under-18 users until counsel and the provider's terms allow it.**

## 6. AI and outside providers

- **No AI provider is currently approved to receive student material.** BUILD does not now send your questions, documents or any data about you to an outside AI provider. [When a provider is approved, this section will name it, say what it receives, where it processes it, how long it keeps it, and the safeguards. **A provider will be listed only after approval, and BUILD will not describe any processing that the provider's own terms do not permit.**]
- **Open provider restrictions.** For example, one provider's developer terms (the Gemini API Additional Terms, effective 2026-03-23, read 2026-11-22 at https://aistudio.google.com/docs/terms) require users to be 18 or older and bar use in a service directed to, or likely to be accessed by, people under 18, with no education exception stated. That question is unresolved, and **no processing will begin until it is answered in writing or the arrangement changes.**
- **If a provider is approved later:** BUILD will keep names, school identifiers and unneeded identifying details out of what it sends, and use pseudonymous or opaque identifiers. These are still personal data, and your own question text and document passages can contain personal data that cannot be removed. This notice will say so.
- **Automated decisions.** BUILD's AI does not assign grades or make decisions with legal or similarly significant effects about you. Scores and results come from fixed rules and your institution's release settings. The NDPC lists a right not to be subject to automated decision-making (https://ndpc.gov.ng/, citing sections 34 to 38, read 2026-11-22); the statute's conditions are **UNVERIFIED**.
- On-device AI is planned for a later release and is not part of this version.

## 7. How long we keep data, and deleting it

**All periods below are placeholders for counsel and the responsible adult.**

| Data | Kept for | Notes |
|---|---|---|
| Account and profile | [PERIOD] after closure | |
| Uploaded files and the data derived from them | Until you delete them, or [PERIOD] after account closure | **Student deletion is not yet available in the app.** It is a known gap, so until it exists this row cannot be promised. When it does, deleting a document must also remove its extracted text and search entries |
| Assessments, attempts and results | [PERIOD, set with the institution] | Academic records may have to be kept for institutional or legal reasons |
| **Tutor conversations** | **Not kept after the session in the first release.** BUILD's first release has no persistent conversation history | A stored history (with its own retention rule and deletion) will be added only after a retention decision, and this notice will change first |
| Security and error logs | [PERIOD] | Logs avoid recording the text of your questions or documents |
| Backups | [PERIOD] | |

**Closing your account.** [Method.] On closure, [WHAT IS DELETED, WHAT IS KEPT AND WHY, AND WHEN].

## 8. Sharing

- **Your institution:** [WHAT THE INSTITUTION CAN SEE, for example membership and academic results released to it; counsel and the institution to define. Whether the university receives your uploads or questions: **no, unless you publish a document to your institution's students**].
- **Other students:** only material you choose to publish. Uploads are private by default.
- **Service providers** that host and run BUILD (cloud hosting, email): [LIST ONLY WHEN SETTLED, with country and role]. Hosting is planned on Google Cloud [confirm; region not chosen].
- **Authorities:** where the law requires.
- **Transfers outside Nigeria:** [COUNSEL: the position. The NDPC describes rules for cross-border transfers (https://ndpc.gov.ng/faqs/, citing sections 41 to 43, read 2026-11-22); the statute text was **not read**.]

## 9. Security

BUILD signs requests between its own services, keeps each university's data separate, checks what you may read before any answer is shown, scans uploads for malware, and limits who can reach the database. No system is perfectly secure. [Counsel and engineering: confirm each statement before publication, and add encryption, access control and backup details that are true.] If a breach is likely to harm you, we will tell you and the regulator as the law requires. [**The notification deadlines are UNVERIFIED.**]

## 10. Your rights

You can ask us to: tell you what we hold about you and how we use it; correct it; erase it; restrict or object to some processing; give you a copy you can move elsewhere; and not be subject to a decision made only by automated means that significantly affects you. The NDPC lists these rights and cites sections 34 to 38 of the Act (https://ndpc.gov.ng/, read 2026-11-22); **the statute text was not read and the conditions on each right are UNVERIFIED.**

To use a right, contact [CONTACT]. We will answer within [PERIOD]. Some data cannot be erased where we must keep it by law or for the institution's academic records; we will say so.

## 11. Complaints

Contact us first at [CONTACT]. You can also complain to the **Nigeria Data Protection Commission** (https://ndpc.gov.ng/, read 2026-11-22). [Counsel: add any other regulator or the institution's route.]

## 12. Changes to this notice

We will tell you in the app [and by email] before a material change [NOTICE PERIOD], and update the date. [Counsel: confirm.]

## 13. Where this notice is published

At [HOSTING LOCATION AND URL]. The mobile app should read the Privacy Policy and Terms addresses from configuration, and a production build should refuse to start without them (relayed by the review session; not verified in the app code). See the Terms, section 18.

## 14. Sources and what could not be verified

Read on 2026-11-22. This is research for counsel, **not legal advice**.

| Source | What it supported | Status |
|---|---|---|
| NDPC home page, https://ndpc.gov.ng/ | Data subject rights listed (cites sections 34 to 38); controller and processor responsibility (section 29); the page links the Act and the 2025 Directive | Summary read; **statute not read** |
| NDPC FAQ, https://ndpc.gov.ng/faqs/ | Scope (section 2); definition of processing (section 65); cross-border transfers (sections 41 to 43); penalties (section 48); annual compliance audit returns by 31 March (GAID 2025, articles 10.7 and 10.8) | Summary read; **statute not read** |
| NDPC resources page, https://ndpc.gov.ng/resources/ | Lists the Act, the Directive and guidance notices | Titles only |
| The General Application and Implementation Directive 2025 (PDF on ndpc.gov.ng) | | **Unreadable** by the page reader; **UNVERIFIED** |
| The full text of the Nigeria Data Protection Act 2023 | | **Not read** |
| Children's data, consent and age verification | | **UNVERIFIED** |
| Registration of controllers of major importance, DPO duty, impact assessments, breach notification deadlines, retention rules | | **UNVERIFIED** |
| Age of majority; the Child's Rights Act 2003 | | **No official source reached; UNVERIFIED** |
| A provider's age rule | https://aistudio.google.com/docs/terms (effective 2026-03-23) | Read in full |

## 15. Placeholders, decisions and reviewers

| # | Placeholder or decision | Who supplies it |
|---|---|---|
| 1 | **Legal entity** (or a statement that BUILD is not yet registered) | The responsible adult |
| 2 | **Data controller**, separate from the legal entity; the roles of BUILD and any university (controller, joint controller, processor) | The responsible adult with counsel |
| 3 | Data Protection Officer and whether required | Counsel |
| 4 | Contact email, address, complaints channel, response times | The responsible adult |
| 5 | Lawful bases for each purpose | Counsel |
| 6 | **Age policy**, age confirmation, guardian process, under-18 safeguards | The responsible adult and counsel |
| 7 | Retention periods and what closure deletes | Counsel and the responsible adult |
| 8 | Whether student deletion will exist before launch, and its scope | Product and engineering |
| 9 | Whether stored tutor conversations will ever exist, and their retention | Product and counsel |
| 10 | Cross-border transfer position | Counsel |
| 11 | Whether a data protection impact assessment is required, and its scope | Counsel |
| 12 | What the institution may see; the data-sharing arrangement with FUTA | The responsible adult, counsel and FUTA |
| 13 | The written answer to the AI-provider age question | The responsible adult |
| 14 | Effective date; notice period; hosting URLs; how acceptance is recorded | The responsible adult and the mobile lead |

| Reviewer | Reviews | Does **not** replace |
|---|---|---|
| **A qualified Nigerian privacy or legal professional** | Both documents: obligations under the Nigeria Data Protection Act, under-18 safeguards, controller responsibilities, retention, consent, user rights | The academic review |
| **A FUTA-authorised academic representative** (separate) | The academic-data arrangements: whether BUILD's use of FUTA academic records and curriculum materials is appropriate | **Legal review** |

Both documents stay **DRAFT — NOT FOR PRODUCTION USE** until the responsible adult or operator and the qualified reviewer confirm the details.
