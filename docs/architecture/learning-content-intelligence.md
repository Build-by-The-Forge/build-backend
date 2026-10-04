# Learning Content Intelligence Architecture (Phase 4B)

## 1. Executive Overview

Learning Content Intelligence (Phase 4B) establishes the authoritative bridge between the **BUILD Backend** (System of Record & Policy Engine) and the **AI Service** (Extraction, OCR, Chunking, Embeddings, & Retrieval Engine).

While Phase 4A defines **"What a student is supposed to learn"** (authoritative national benchmark and institutional effective curriculum), Phase 4B establishes **"What verified educational content BUILD has available to teach it."**

---

## 2. Bounded Context Map & Responsibility Matrix

```text
┌────────────────────────────────────────────────────────────────────────┐
│                             BUILD BACKEND                              │
│                      (System of Record & Policy)                       │
├────────────────────────────────────────────────────────────────────────┤
│ • Content Source Registry (Who supplied it? Authority level? Scope?)    │
│ • Content Asset Lifecycle (Storage URI, SHA-256, MIME, Versioning)     │
│ • Processing Job Orchestration (Queuing, State transitions, Retries)   │
│ • Authoritative Curriculum Linkage (Course, Topic, Learning Outcome)   │
│ • Tenant Isolation & RBAC (University, Faculty, Department, Role)      │
│ • Access Control for Retrieval (Student Read Mode vs. Staff vs. Admin) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         REST / JSON Ingestion Contract
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                              AI SERVICE                                │
│                   (Extraction, Parsing & Reasoning)                    │
├────────────────────────────────────────────────────────────────────────┤
│ • Document Structure Extraction & Parsing (PDF, DOCX, PPTX, Web)       │
│ • Optical Character Recognition (OCR) for scanned sheets/diagrams      │
│ • Text Normalization & Markdown Sanitization                           │
│ • Semantic Chunking & Token Windowing                                  │
│ • Dense/Sparse Vector Embeddings Generation                            │
│ • Concept Classification & Suggested Curriculum Tagging                │
│ • Vector Indexing & RAG Retrieval Pipelines                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Domain Entities & Hierarchy

```text
ContentSource (Origin & Trust Authority)
   │
   ├── ContentAsset (Physical/Digital Object: PDF, PPTX, URL)
   │      │
   │      ├── IngestionJob (Asynchronous Processing Execution & State)
   │      │
   │      ├── ContentChunk (Extracted Text Fragment with Page & Heading)
   │      │
   │      └── CurriculumContentLink (Mapped Course, Topic, Outcome)
```

### 3.1. ContentSource
Represents the origin, ownership, and trust boundary of educational material.

* **Attributes**:
  * `id: str` (e.g. `csrc-uuid`)
  * `tenant_id: str | None` (None = Platform/Global like CCMAS; string = University-scoped)
  * `source_type: ContentSourceType`
    * `CCMAS`: Regulatory national benchmark documentation
    * `TEXTBOOK`: Publisher/academic textbook
    * `LECTURER_UPLOAD`: Course notes, lecture slides, syllabus
    * `ADMIN_UPLOAD`: University-wide reference material
    * `COURSE_MATERIAL`: Handouts, lab manuals
    * `WEB_SOURCE`: Curated educational article or documentation
  * `authority_level: AuthorityLevel`
    * `REGULATORY`: Tier 1 national curriculum baseline
    * `INSTITUTIONAL`: University/Department official teaching material
    * `APPROVED_REFERENCE`: Peer-reviewed/faculty-approved textbook
    * `EXTERNAL`: Verified third-party reference
    * `USER_PROVIDED`: Unverified supplementary material
    * `AI_DERIVED`: Synthesized content (explicitly non-authoritative)
  * `title: str`
  * `author: str | None`
  * `publisher: str | None`
  * `isbn_or_doi: str | None`
  * `source_url: str | None`
  * `created_by: str`
  * `created_by_email: str`
  * `visibility: VisibilityScope` (`PLATFORM`, `TENANT`, `FACULTY`, `DEPARTMENT`, `PROGRAMME`, `COURSE_ONLY`)
  * `status: SourceStatus` (`ACTIVE`, `DEPRECATED`, `REVOKED`)

### 3.2. ContentAsset
Represents a specific physical file or URL snapshot associated with a `ContentSource`.

* **Attributes**:
  * `id: str` (e.g. `cass-uuid`)
  * `source_id: str`
  * `tenant_id: str | None`
  * `file_name: str`
  * `mime_type: str`
  * `file_size_bytes: int`
  * `content_sha256: str` (Deterministic SHA-256 for deduplication)
  * `storage_uri: str` (e.g. `s3://build-content/futa/csc101/lecture1.pdf`)
  * `asset_version: int` (Incremented on replacement)
  * `ingestion_status: IngestionStatus`
    * `UPLOADED` $\to$ File placed in storage
    * `QUEUED` $\to$ Ingestion job dispatched
    * `PROCESSING` $\to$ AI Service actively parsing/OCR
    * `EXTRACTED` $\to$ Text and sections extracted
    * `CHUNKED` $\to$ Chunks and semantic tokens generated
    * `INDEXED` $\to$ Vectors embedded and indexed in vector store
    * `READY` $\to$ Active and available for student Read Mode / AI retrieval
    * `FAILED` $\to$ Terminal processing failure with error log
  * `error_code: str | None`
  * `error_message: str | None`

### 3.3. ContentProcessingJob
Tracks the idempotent execution of background extraction and indexing.

* **Attributes**:
  * `id: str` (e.g. `cjob-uuid`)
  * `asset_id: str`
  * `tenant_id: str | None`
  * `job_status: JobStatus` (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`)
  * `retry_count: int`
  * `max_retries: int`
  * `processing_pipeline_version: str` (e.g. `"1.0.0"`)
  * `started_at: datetime | None`
  * `completed_at: datetime | None`
  * `job_metadata: dict[str, Any]` (Parser settings, OCR flags, token metrics)

### 3.4. ContentChunk
Represents a clean, indexed semantic text fragment extracted by the AI Service and persisted in the backend for authoritative retrieval.

* **Attributes**:
  * `id: str` (e.g. `chnk-uuid`)
  * `asset_id: str`
  * `chunk_index: int`
  * `page_number: int | None`
  * `section_heading: str | None`
  * `chunk_text: str`
  * `chunk_sha256: str`
  * `token_count: int`
  * `metadata: dict[str, Any]` (Code blocks, table indicators, formulas)

### 3.5. CurriculumContentLink
Binds content chunks and assets to the 3-Tier Curriculum structure established in Phase 4A.

* **Attributes**:
  * `id: str` (e.g. `clnk-uuid`)
  * `tenant_id: str`
  * `programme_id: str`
  * `course_code: str` (e.g. `COS102`)
  * `topic_id: str | None`
  * `outcome_id: str | None`
  * `asset_id: str`
  * `chunk_id: str | None`
  * `link_type: LinkType` (`PRIMARY_TEXT`, `LECTURE_NOTE`, `SUPPLEMENTARY`, `EXERCISE`)
  * `alignment_status: AlignmentStatus`
    * `AI_SUGGESTED`: Proposed automatically by model classification
    * `HUMAN_CONFIRMED`: Verified by lecturer or departmental coordinator
    * `SYSTEM_CONFIRMED`: Direct upload explicitly mapped by instructor
  * `confirmed_by: str | None`

---

## 4. Backend $\leftrightarrow$ AI Service Ingestion Contract

### 4.1. Processing Request (`POST /internal/content/process`)
Dispatched by the backend to trigger document extraction.

```json
{
  "job_id": "cjob-9f3a-4b12",
  "asset_id": "cass-12e4-5678",
  "tenant_id": "futa-test",
  "source_type": "LECTURER_UPLOAD",
  "authority_level": "INSTITUTIONAL",
  "storage_uri": "s3://build-content/futa/cos102/week4.pdf",
  "mime_type": "application/pdf",
  "content_sha256": "3a7bd8...64char",
  "parser_options": {
    "enable_ocr": true,
    "extract_tables": true,
    "extract_formulas": true,
    "target_chunk_tokens": 512,
    "chunk_overlap_tokens": 64
  },
  "curriculum_context": {
    "programme_id": "prog-csc",
    "course_code": "COS102",
    "course_title": "Problem Solving & Programming"
  }
}
```

### 4.2. Processing Response
Returned by the AI Service upon processing completion.

```json
{
  "job_id": "cjob-9f3a-4b12",
  "asset_id": "cass-12e4-5678",
  "status": "COMPLETED",
  "document_summary": {
    "total_pages": 24,
    "total_chunks": 48,
    "total_tokens": 14200,
    "language": "en",
    "ocr_applied": false
  },
  "chunks": [
    {
      "chunk_index": 1,
      "page_number": 1,
      "section_heading": "1. Introduction to Algorithms",
      "chunk_text": "An algorithm is a finite sequence of well-defined instructions...",
      "chunk_sha256": "8f4e21...",
      "token_count": 280,
      "suggested_topic_titles": ["Algorithms", "Problem Formulation"]
    }
  ],
  "suggested_curriculum_alignments": [
    {
      "course_code": "COS102",
      "topic_sequence": 1,
      "confidence_score": 0.94
    }
  ]
}
```

---

## 5. Deduplication & Content Versioning Invariants

1. **SHA-256 Content Deduplication**:
   - If an uploaded file matches an existing `content_sha256` within the same tenant/course, the system reuses existing parsed chunks and creates an alias link rather than duplicating storage and processing workloads.
2. **Deterministic Versioning**:
   - Uploading a new edition of a textbook or an updated slide deck increments `asset_version` while preserving historical link bindings for past academic sessions.
3. **Tenant Isolation**:
   - A lecturer upload at University A is strictly isolated by `tenant_id` and never leakable into University B's search index or Read Mode context.

---

## 6. Phase 4B Implementation Slices

```text
4B.1  Content Source Registry & Authority Model
      ├─ ContentSource Aggregate, Enums (SourceType, AuthorityLevel, VisibilityScope)
      ├─ Migration & DB Models for content_sources
      └─ Domain & Application Handlers for Source Registration

4B.2  Content Asset & Storage Metadata
      ├─ ContentAsset Aggregate & SHA-256 Deduplication Logic
      ├─ Migration & DB Models for content_assets
      └─ Asset Creation & Storage URI Registration Handlers

4B.3  Ingestion Jobs & Lifecycle State Machine
      ├─ IngestionJob Aggregate & Status Transitions (QUEUED -> PROCESSING -> READY/FAILED)
      ├─ Migration & DB Models for content_ingestion_jobs
      └─ Asynchronous Job Orchestration & Failure Recovery

4B.4  Backend ↔ AI Service Ingestion Gateway & Contract
      ├─ AIServiceClient Port & HttpAIServiceGateway
      ├─ Request/Response DTOs & Validation Schemas
      └─ Mock & Integration Test Harness for AI Service Processing

4B.5  Extracted Chunks & Semantic Metadata Store
      ├─ ContentChunk Aggregate & DB Models for content_chunks
      └─ Chunks Persistence & Token Statistics Handlers

4B.6  Curriculum & Topic Alignment
      ├─ CurriculumContentLink Aggregate (Linking to 4A Effective Curriculum)
      ├─ DB Models & Migration for curriculum_content_links
      └─ Alignment Handlers (AI Suggested vs. Instructor Confirmed)

4B.7  Lecturer & Admin Content Management APIs
      ├─ REST Endpoints for Upload, Source Registry, Alignment, and Status
      └─ RBAC Protection (CURRICULUM_SOURCE_MANAGE, CATALOGUE_UPDATE)

4B.8  Student Read Mode Retrieval Gateway
      ├─ Topic-Scoped Content Retrieval API (Filtered by Tenant & Effective Curriculum)
      └─ Student Access Permission Enforcement (CATALOGUE_READ)
```
