# Mobile capability and gap inventory (M0)

**Surveyed on 2026-10-30, at build-backend `fac0114`, ai-service `208ea52` and Build-UI `9484e9f`.**

**This comes from reading the code. No route was called for it.** Each gap is a finding to confirm: M2 turns this list into the machine-readable allowlist and CI drift gate, and a test there settles anything this reading got wrong. Rules referred to here are in the [conventions](mobile-api-conventions.md).

**Summary:** most student reads exist. Three things block the planned journeys: students can't upload, students can apparently see unpublished assessments, and chat returns no citations.

## Student capabilities

"Permission" is what the route requires. Every one is held by the `student` role unless marked **no**. "Gaps" refers to the table further down.

### Identity and session

| Capability | Route | Permission | Gaps |
|---|---|---|---|
| Register | `POST /identity/users` | None | G-14 |
| Sign in | `POST /identity/authenticate` | None | G-14 |
| Refresh | `POST /identity/refresh` | Refresh token | G-14 |
| Sign out | `POST /identity/logout`, `/logout-all` | Signed in | |
| Current user | `GET /identity/me` | Signed in | |
| Memberships | `GET /identity/memberships` | Signed in | |
| Verify email | `POST /identity/verify-email`, `/resend-verification` | None | G-14 |
| Recover password | `POST /identity/forgot-password`, `/reset-password` | None | G-14 |
| Change password | `POST /identity/change-password` | Signed in | G-14 |
| Join a tenant (Decision C) | `POST /tenants/{slug}/join`, `GET /tenants/{slug}/join-policy`, `POST /invitations/accept` | Verified user | |

### Academic reads

| Capability | Route | Permission | Gaps |
|---|---|---|---|
| Courses | `GET /catalogue/courses/`, `/catalogue/courses/{id}` | `catalogue.read` | G-08, G-10 |
| Topics | `GET /catalogue/courses/{id}/topics` | `catalogue.read` | G-10 |
| Learning outcomes | `GET /catalogue/topics/{id}/learning-outcomes` | `catalogue.read` | G-10 |
| Reference materials | `GET /catalogue/topics/{id}/reference-materials` | `catalogue.read` | G-10 |
| Faculties, departments, programmes | **None** | | G-09 |

### Content and ingestion

| Capability | Route | Permission | Gaps |
|---|---|---|---|
| List sources | `GET /content/sources` | `content.source.read` | G-05 |
| Upload | `POST /content/sources/{id}/assets/upload` | `content.asset.upload`: **no** | G-01, G-02, G-06, G-11 |
| Start ingestion | `POST /content/assets/{id}/jobs` | `content.job.manage`: **no** | G-01, G-07 |
| Job status | `GET /content/jobs/{id}`, `/content/assets/{id}/jobs/latest` | `content.job.read` | G-05, G-06 |
| Asset details and lists | `GET /content/assets/{id}`, `/content/assets`, `/content/sources/{id}/assets` | `content.asset.read` | G-05, G-06 |
| Retry a failed job | `POST /content/jobs/{id}/retry`, `/content/assets/{id}/reprocess` | `content.job.manage`: **no** | G-12 |
| Reopen a document | **None** | | G-13 |

### Assessments

| Capability | Route | Permission | Gaps |
|---|---|---|---|
| List and view | `GET /assessment/assessments`, `/assessments/{id}` | `assessment.read` | G-03, G-10 |
| Start attempt | `POST /assessment/assessments/{id}/attempts` | `assessment.attempt.start` | |
| List and view attempts | `GET /assessment/attempts`, `/attempts/{id}` | `assessment.attempt.read` | G-10 |
| Questions | `GET /assessment/attempts/{id}/questions` | `assessment.attempt.read` | |
| Save or remove an answer | `PUT`, `DELETE /assessment/attempts/{id}/answers/{question_id}` | `assessment.attempt.answer.write`, `.delete` | |
| Read answers | `GET /assessment/attempts/{id}/answers` | `assessment.attempt.read` | |
| Submit | `POST /assessment/attempts/{id}/submit` | `assessment.attempt.submit` | G-15 |
| Result | `GET /assessment/attempts/{id}/result` | `assessment.attempt.result.read` | G-16 |

The attempt's question payload has a prompt, marks and option text, and no answer key.

### AI

| Capability | Route | Permission | Gaps |
|---|---|---|---|
| Chat | `POST /ai/chat` | `ai.use` | G-04, G-17, G-18, G-19 |
| Conversations | **None** | | G-17 |

## Gaps

"Kind" follows the split M2 enforces: a **contract** gap means the capability works but its shape is wrong; an **implementation** gap means the behaviour doesn't exist or is wrong. Severity is about the first release.

| ID | Kind | Severity | Gap | Evidence | Closes in |
|---|---|---|---|---|---|
| G-01 | Implementation | Blocker | Students can't upload or start ingestion | `app/core/authorization.py`, `student` role | M3-D, Decision B |
| G-02 | Implementation | Blocker | Upload needs a source, and students can't create one | `POST /content/sources` needs `content.source.manage` | M3-D, Decision B |
| G-03 | Implementation | **High** | Assessment list and detail apply no status filter, so a student appears able to read draft assessments, including question prompts and options | `list_all`, `list_by_course` in `app/infrastructure/assessment/repositories.py`; `ListAssessmentsHandler` | M3-E. **Confirm first** |
| G-04 | Implementation | **High** | Chat answers carry no citations: the backend gateway keeps `answer` and context text, and drops `citations` and `grounded`, which the AI service already returns | `app/infrastructure/ai/assistant_gateway.py` | M3-F, M4 |
| G-05 | Implementation | **High** | Retrieval isn't limited to `ready` documents, or to what this user may read. Known limitation from the Phase 3 record | ai-service `retrieval.py`, `tenanted_retriever.py` | M4 |
| G-06 | Contract | **High** | Student-readable responses expose internals: `storage_uri`, `created_by_email`, `external_task_id`, `attempt_history`, `error_details`, `metrics` | `asset_schemas.py`, `job_schemas.py` | M3-D |
| G-07 | Contract | Medium | Clients can set `max_attempts` and `correlation_id` when creating a job. Whether a repeat creates a second job needs checking | `job_schemas.py` | M3-D |
| G-08 | Implementation | Medium | The course list catches every exception and returns its text to the client | `app/api/catalogue/courses.py:38` | M3-A |
| G-09 | Implementation | Medium | No read routes for faculties, departments or programmes, though the domain and tables exist. Onboarding needs them (PRD §300) | `app/domain/tenant/` has them; `app/api/` doesn't | M3-C |
| G-10 | Contract | Medium | Courses, topics, outcomes, assessments and attempts aren't paginated. Whether students can see draft courses needs the same check as G-03 | `courses.py`, `attempts.py` | M3-C, M3-E |
| G-11 | Implementation | Medium | The 60-second read limit makes large uploads fail on slower connections | Decision D | M3-D |
| G-12 | Implementation | Medium | "Retry available" has no student action | `content.job.manage` required | M3-D |
| G-13 | Implementation | Medium | No route returns a document to a student, so PRD Journeys C and D can't finish | `app/api/content/` | Decide in M1 |
| G-14 | Contract | Medium | Identity bodies are untyped `dict[str, str]`, so the contract can't describe them and a missing field becomes a business error instead of a validation error | `app/api/identity.py` | M3-B |
| G-15 | Contract | Medium | What a repeated submit returns isn't defined | `attempt_handlers.py` | M3-E |
| G-16 | Contract | Medium | Results, including each question's `is_correct`, are returned straight after submission. The policy needs stating, especially if an assessment can be retaken | `attempts.py`, `get_attempt_result` | M1 |
| G-17 | Implementation | Medium | No conversations | Decision A | M3-F |
| G-18 | Contract | Medium | Chat returns raw `context` passages, including uncited ones | `app/api/ai.py` | M3-F |
| G-19 | Contract | Low | Chat has no way to limit a question to one course or document (context selection, PRD §303) | `ChatRequest` | Decide in M1 |
| G-20 | Contract | **High** | Mobile routes return at least three shapes: `{success, data, meta}`, `{data}`, and `{error}`. Errors have no stable codes except on content routes | `exceptions.py`, `jobs.py`, `assets.py` | M3-A |
| G-21 | Contract | Medium | Validation errors return Pydantic's output as is, which includes the submitted `input` | `validation_exception_handler` | M3-A |
| G-22 | Contract | Low | `X-Request-ID` is accepted with no format or length check | `app/core/middleware.py:22` | M3-A |
| G-23 | Contract | Low | Asset ordering has no unique tie-breaker | `asset_repositories.py:91` | M3-D |
| G-24 | Implementation | Low | OpenAPI is generated only when `api_docs_enabled` is on, so M2 needs a build-time export | `app/core/config.py` | M2 |

## Already sound

Worth keeping as they are:

- Tenant denial doesn't distinguish an unknown tenant from a non-member.
- Upload idempotency, size limits enforced while reading, and type detection from the bytes.
- Starting an attempt returns the active one, and only published assessments can be attempted.
- Refresh rotation with reuse detection.
- The AI service already produces grounded answers with citations. It's the backend that doesn't relay them.

## The mobile app today

For M5 and M6. There's no API client, and the app has these local behaviours to replace:

| Area | Today | Replaced by |
|---|---|---|
| Sign-in | Routes to onboarding with no authentication | M6 |
| Tokens | No secure storage; `expo-secure-store` isn't installed | M5 |
| AI chat | `src/app/dashboard/buildai.tsx` posts `{messages}` to a configurable endpoint and expects `{reply}`, which isn't the backend's contract | M6 |
| Uploads | `src/services/studyShelf.ts` is local only, so its "uploaded" isn't a server state | M6 |
| Campus map | Bundled MapLibre map | Unaffected |
