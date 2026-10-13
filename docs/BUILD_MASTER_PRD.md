# BUILD

## Master Product & Technical Product Requirements Document

**Product:** BUILD — AI Academic Intelligence Platform
**Document:** Master Product & Technical PRD
**Version:** 2.0
**Status:** Draft — Consolidated Product & Architecture Baseline
**Primary Launch Institution:** Federal University of Technology, Akure (FUTA)
**Initial Academic Session:** 2025/2026
**Architecture Strategy:** Multi-tenant, FUTA-first
**Primary Client:** React Native
**Backend:** FastAPI
**Primary Database:** PostgreSQL
**AI Platform:** BUILD AI Service
**Initial Foundation Model:** Meta Muse Glimmer 30B through Together AI
**Model Strategy:** Provider-agnostic Model Gateway

---

# 1. Document Purpose

This document defines the product vision, functional requirements, technical architecture, data architecture, AI architecture, academic intelligence model, governance principles, operational requirements, monetization model, and implementation direction for BUILD.

It is intended to serve as the primary source of truth for BUILD product and engineering decisions.

The document reconciles:

1. The original BUILD product vision.
2. The intended student experience.
3. The academic intelligence architecture.
4. The current backend and AI-service implementations.
5. Findings from repository audits.
6. FUTA academic structure and CCMAS requirements.
7. AI, RAG, OCR, agent, memory, model, and evaluation requirements.
8. Campus GIS and Map requirements.
9. Content acquisition and academic material ingestion.
10. Multi-role and multi-tenant architecture.
11. Subscription and entitlement strategy.
12. Security, governance, observability, and cost controls.
13. Future personalization and intelligence capabilities.

This document is not intended to freeze implementation details unnecessarily. Where implementation technology may change, the PRD defines the required capability and architectural boundary rather than prescribing an irreversible implementation.

---

# 2. Product Vision

BUILD is an AI-powered academic intelligence platform designed to become the primary academic companion for university students.

### Product positioning

> **The most intelligent academic companion for FUTA students — built to transform how students learn, study, and excel.**

BUILD is not merely:

* a CBT application,
* an AI chatbot,
* a document repository,
* a learning management system,
* a video platform,
* or a campus map.

It is an integrated academic intelligence system connecting:

**Curriculum → Content → Knowledge → Learning → Assessment → Performance → AI → Personalization.**

The initial deployment focuses on FUTA while the underlying architecture is designed for multiple universities and organizations.

---

# 3. Product Mission

BUILD shall help students:

* understand what they are expected to learn;
* access structured academic knowledge;
* learn through text and video;
* practise through CBT;
* ask questions and receive grounded AI assistance;
* upload and process academic materials;
* discover relevant academic resources;
* understand their strengths and weaknesses;
* prepare intelligently for examinations;
* collaborate with other students;
* navigate campus;
* and progressively receive more personalized academic assistance.

The long-term objective is to create an **AI-native academic operating system**, not simply a collection of educational features.

---

# 4. Product Principles

BUILD shall follow these principles.

## 4.1 Student-first

The product must maximize academic value before monetization.

Students must be able to use BUILD meaningfully without immediately paying.

## 4.2 Evidence-first AI

AI should prefer retrieved, verified academic evidence over unsupported generation.

If evidence is insufficient, BUILD should communicate uncertainty rather than fabricate academic information.

## 4.3 Curriculum-first intelligence

The curriculum is the organizing structure of the academic system.

Documents, videos, questions, concepts, learning objectives, and student performance should connect back to academic structure wherever possible.

## 4.4 AI is an intelligence layer

The AI service should enhance the platform rather than becoming the system of record.

The backend remains authoritative for:

* identity;
* tenancy;
* permissions;
* academic entities;
* assessments;
* progress;
* subscriptions;
* business rules;
* and transactional state.

## 4.5 Model independence

BUILD shall not be architecturally dependent on one foundation-model provider.

## 4.6 Provenance everywhere

Academic knowledge should retain its origin.

BUILD should know whether information came from:

* CCMAS;
* FUTA;
* lecturer material;
* student contribution;
* past examination;
* uploaded document;
* uploaded video;
* licensed/open resource;
* AI generation;
* or another approved source.

## 4.7 Confidence-aware intelligence

AI extraction, classification, alignment, and reasoning should expose confidence internally.

Low-confidence operations should trigger clarification or human review.

## 4.8 Human governance

High-impact academic changes should not silently become authoritative because an AI model generated them.

## 4.9 Privacy by design

User identity, academic activity, uploaded content, analytics, and AI interactions should be handled according to least privilege and appropriate data protection requirements.

## 4.10 Build for evolution

The platform should support future:

* universities;
* curricula;
* AI models;
* learning modes;
* payment providers;
* storage providers;
* GIS providers;
* and personalization systems.

---

# 5. Problem Statement

University students frequently experience fragmented academic workflows.

Relevant knowledge may be distributed across:

* lecture notes;
* PDFs;
* textbooks;
* WhatsApp groups;
* past questions;
* lecturer materials;
* YouTube videos;
* departmental resources;
* personal notes;
* and disconnected websites.

Students often lack:

* a structured view of their curriculum;
* an intelligent academic search layer;
* reliable academic explanations;
* personalized practice;
* meaningful performance analysis;
* integrated academic content;
* and an intelligent relationship between what they study and what they are assessed on.

BUILD exists to unify these experiences.

---

# 6. Target Users

## 6.1 Student

Primary user.

Capabilities include:

* academic discovery;
* Read Mode;
* Video Mode;
* CBT Mode;
* AI Tutor;
* uploads;
* progress;
* analytics;
* groups;
* leaderboard;
* campus map;
* academic search;
* personalized learning.

## 6.2 Lecturer / Contributor

Authorized academic contributor.

Capabilities may include:

* uploading course materials;
* uploading videos;
* contributing questions;
* reviewing generated content;
* verifying content;
* managing scoped academic materials;
* viewing authorized course analytics.

## 6.3 Academic Administrator

Responsible for academic governance.

Capabilities include:

* curriculum management;
* content moderation;
* question governance;
* academic verification;
* programme/course administration;
* academic analytics;
* CCMAS synchronization;
* approval workflows.

## 6.4 Owner / Tenant Administrator

University/organization-level operator.

Capabilities include:

* organization configuration;
* memberships;
* permissions;
* analytics;
* integrations;
* subscriptions;
* governance;
* audit;
* system configuration.

---

# 7. Identity Model

A user account and an academic membership are separate concepts.

One account may have multiple organization-scoped memberships.

Example:

```text
Account
│
├── FUTA / Student
│
└── Another Organization / Lecturer
```

Roles should therefore be determined by:

**Account + Organization Membership + Scope + Permissions**

rather than by creating separate accounts for each role.

This permits a future user to legitimately have multiple roles without duplicating identity records.

---

# 8. Multi-Tenant Architecture

BUILD shall be multi-tenant by architecture even though initial deployment is FUTA-focused.

Primary tenancy boundary:

```text
Organization / University
        ↓
School
        ↓
Department / Academic Unit
        ↓
Programme
        ↓
Academic Membership
```

Tenant isolation must be enforced server-side.

Client-supplied tenant identifiers must never be treated as authoritative without authenticated authorization context.

---

# 9. FUTA Academic Foundation

The initial academic catalogue shall support the current FUTA structure.

## 9.1 Schools and programmes

### SOC — School of Computing

* CSC — Computer Science
* CYS — Cyber Security
* IFS — Information Systems
* IFT — Information Technology
* SEN — Software Engineering
* DTS — Data Science

### SAAT — School of Agriculture and Agricultural Technology

* AEC — Agricultural Extension and Communication Technology
* ARE — Agricultural Resources Economics
* APH — Animal Production and Health
* CSP — Crop, Soil and Pest Management
* EWM — Ecotourism and Wildlife Management
* FAT — Fisheries and Aquaculture Technology
* FST — Food Science and Technology
* FWT — Forestry and Wood Technology
* NTD — Nutrition and Dietetics

### SIMME — School of Infrastructure, Minerals and Manufacturing Engineering

* AGE — Agricultural Engineering
* CVE — Civil Engineering
* IPE — Industrial and Production Engineering
* MEE — Mechanical Engineering
* MNE — Mining Engineering
* MME — Metallurgical and Materials Engineering

### SET — School of Environmental Technology

* BDG — Building Technology
* ESM — Estate Management
* IDD — Industrial Design
* QSV — Quantity Surveying
* URP — Urban and Regional Planning
* SVG — Surveying and Geoinformatics

Architecture is not treated as a SET programme in the canonical model.

### SOA — School of Architecture

* ARC — Architecture
* AST — Architectural Science Technology
* FUD — Furniture Design
* IAD — Interior Architecture Design
* LAR — Landscape Architecture
* NAR — Naval Architecture

### SEMS — School of Earth and Mineral Sciences

* AGY — Applied Geology
* AGP — Applied Geophysics
* MST — Marine Science and Technology
* MCS — Meteorology and Climate Science
* RSG — Remote Sensing and Geoinformatics

### SLIT — School of Logistics and Innovation Technology

* PMT — Project Management Technology
* TMT — Logistics and Transport Management Technology
* ENT — Entrepreneurship Management Technology
* PRT — Procurement Management Technology
* FIN — Financial Technology

### SPS — School of Physical Sciences

* IMC — Industrial Chemistry
* PHY — Physics
* MTS — Mathematical Sciences
* STA — Statistics

Industrial Mathematics must not be represented as a separate programme.

### SLS — School of Life Sciences

* BCH — Biochemistry
* BIO — Biology
* MCB — Microbiology
* BTC — Biotechnology

### SESE — School of Electrical and Systems Engineering

* EEE — Electrical and Electronics Engineering
* CPE — Computer Engineering
* ICE — Information and Communication Engineering
* BME — Biomedical Engineering

### SSTE — School of Science and Technology Education

* EDT — Educational Technology
* LIS — Library and Information Science
* ITE — Industrial and Technology Education

---

# 10. Academic Structure

BUILD shall distinguish:

```text
University
→ School
→ Department / Academic Unit
→ Programme
→ Programme Code
→ Level
→ Session
→ Semester
→ Course
→ Topic
→ Subtopic
→ Concept
→ Learning Objective
```

The system must not infer authoritative department relationships where the source data does not establish them.

Academic structure should support:

* current curriculum;
* historical curriculum;
* curriculum versions;
* university-specific adoption;
* CCMAS baseline;
* FUTA overrides.

---

# 11. CCMAS and Curriculum Intelligence

CCMAS shall be treated as a major national academic framework, while FUTA implementation shall remain separately represented.

BUILD shall preserve:

```text
CCMAS Standard
       +
FUTA Adoption / Override
       =
Effective Curriculum
```

The system must not flatten these into one irreversible dataset.

## 11.1 Curriculum Intelligence Pipeline

```text
CCMAS / FUTA Sources
        ↓
Source Discovery
        ↓
Scraper / Collector
        ↓
Raw Documents
        ↓
Extraction
        ↓
Curriculum Normalization
        ↓
Validation
        ↓
Candidate Curriculum
        ↓
Review / Approval
        ↓
Canonical Curriculum
```

Scraped information must not directly overwrite production curriculum.

## 11.2 Curriculum versioning

Curricula must be versioned by session or effective period.

Example:

```text
2025/2026 Curriculum
2026/2027 Curriculum
```

Historical students, questions, and documents must remain linked to the curriculum context under which they were valid.

---

# 12. Academic Knowledge Graph

BUILD shall maintain a structured relationship between:

* curriculum;
* courses;
* topics;
* concepts;
* documents;
* videos;
* questions;
* learning objectives;
* students;
* progress;
* performance.

Example:

```text
CSC 201
  ↓
Data Structures
  ↓
Linked Lists
  ↓
Singly Linked List
  ├── Lecture Note
  ├── Video Chapter
  ├── Past Questions
  ├── AI Questions
  ├── Learning Objectives
  └── Student Performance
```

This graph becomes the foundation for:

* retrieval;
* recommendations;
* tutoring;
* question generation;
* progress analysis;
* personalization;
* academic search;
* and future intelligent planning.

---

# 13. Learn / Study Experience

Learn/Study shall contain three first-class learning modes:

1. **Read Mode**
2. **Video Mode**
3. **CBT Mode**

These are different representations of the same underlying academic knowledge system.

---

# 14. Read Mode

Read Mode provides structured academic learning.

Hierarchy:

```text
Course
 ↓
Topic
 ↓
Subtopic
 ↓
Concept
```

Capabilities:

* structured content;
* AI summaries;
* key points;
* examples;
* exam relevance;
* learning objectives;
* progress tracking;
* related videos;
* related CBT questions;
* AI explanation.

Read Mode should not simply display raw uploaded PDFs.

BUILD should transform appropriate content into structured academic learning experiences.

---

# 15. Video Mode

Video Mode is a first-class academic learning mode.

It shall not be treated merely as a generic media player.

Students should be able to:

* browse academic videos by course;
* browse by topic;
* play videos;
* resume from previous position;
* view chapters;
* view transcripts where available;
* access summaries;
* view key concepts;
* connect videos to Read Mode;
* access related CBT questions;
* track video progress.

## 15.1 Video content relationships

A video may be associated with:

* university;
* school;
* department;
* programme;
* level;
* semester;
* session;
* course;
* topic;
* subtopic;
* curriculum version;
* lecturer/contributor;
* source;
* verification state.

## 15.2 Video ingestion

Authorized administrators and owners shall be able to upload academic videos.

Future authorized lecturers/contributors may receive scoped upload permissions.

Pipeline:

```text
Video Upload
    ↓
Validation
    ↓
Metadata Extraction
    ↓
Media Normalization / Transcoding
    ↓
Thumbnail Generation
    ↓
Audio Extraction
    ↓
Speech-to-Text
    ↓
Transcript
    ↓
Chapter Detection
    ↓
Topic / Concept Extraction
    ↓
Curriculum Alignment
    ↓
Summary
    ↓
Learning Objectives
    ↓
Candidate Questions
    ↓
Review
    ↓
Publish
```

## 15.3 Video as academic knowledge

The video itself is the media representation.

Its transcript, chapters, concepts, metadata, and extracted knowledge become searchable academic evidence.

This allows questions such as:

> “Explain the part of the video where linked lists were introduced.”

to be answered through grounded retrieval.

## 15.4 Video-generated questions

AI may generate candidate practice questions from approved video content.

Generated questions must remain explicitly marked:

```text
source_type = AI_GENERATED
source_video = <video>
verification_status = PENDING
```

They must not silently become official examination questions.

---

# 16. CBT Mode

CBT Mode provides:

* practice;
* past questions;
* AI-generated questions;
* assessments;
* scoring;
* explanations;
* performance analytics.

Question sources shall include:

* PAST_EXAM;
* OFFICIAL;
* CONTRIBUTED;
* AI_GENERATED.

The system must preserve the source and provenance of every question.

---

# 17. Question Intelligence

Questions should support rich metadata.

Required or recommended fields include:

* course;
* topic;
* subtopic;
* learning objective;
* curriculum version;
* programme;
* level;
* semester;
* session;
* source;
* year;
* question type;
* difficulty;
* cognitive level;
* correct answer;
* distractors;
* explanation;
* confidence;
* verification state;
* verification method;
* generated_by;
* source document/video.

Bloom-style cognitive classification may be used.

---

# 18. AI Question Generation

Pipeline:

```text
Course / Topic
      ↓
Learning Objectives
      ↓
Retrieved Evidence
      ↓
Generation
      ↓
Schema Validation
      ↓
Answer Validation
      ↓
Difficulty Estimation
      ↓
Duplicate Detection
      ↓
Curriculum Alignment
      ↓
Quality Evaluation
      ↓
Persistence
      ↓
Review / Approval where required
```

AI-generated questions must never be represented as official or past questions unless independently verified and explicitly classified as such.

---

# 19. Deterministic Answer Verification

Where possible, answers should be validated using deterministic mechanisms.

Examples:

* mathematics;
* numerical physics;
* chemistry calculations;
* programming;
* structured logic.

LLM self-evaluation should not be the only source of truth when deterministic validation is possible.

---

# 20. AI Tutor

BUILD AI Tutor shall provide:

* explanations;
* question answering;
* document-grounded tutoring;
* concept explanations;
* exam preparation;
* learning assistance;
* study planning;
* content discovery;
* related-resource recommendations.

The tutor should understand academic context including:

* student programme;
* level;
* semester;
* course;
* topic;
* curriculum version;
* relevant study history where authorized.

---

# 21. AI Intelligence Architecture

The AI service shall implement an intelligence loop conceptually following:

```text
Understand
→ Remember
→ Research
→ Analyze
→ Reason
→ Plan
→ Create
→ Evaluate
→ Act
→ Monitor
→ Measure
→ Learn
→ Adapt
→ Repeat
```

The runtime must remain bounded by:

* permissions;
* budgets;
* timeouts;
* tool limits;
* model limits;
* authorization;
* safety policies.

---

# 22. Agent Runtime

The AI service shall contain an agent runtime responsible for:

* agent registration;
* lifecycle;
* execution;
* cancellation;
* deadlines;
* budgets;
* tool execution;
* result handling;
* observability.

AI agents shall not receive unrestricted database access.

They should interact with controlled tools.

---

# 23. AI Tool Architecture

Tools may include:

* academic search;
* course search;
* curriculum lookup;
* document search;
* video search;
* progress lookup;
* study-plan creation;
* question generation;
* campus search;
* nearby-location search;
* distance calculation;
* route calculation;
* user-specific academic tools.

Sensitive mutations must require authorization.

---

# 24. Agent Permission Model

Tools shall be categorized by permission.

Examples:

```text
READ
WRITE
SENSITIVE_WRITE
ADMIN
ACADEMIC_REVIEW
OWNER
```

An AI agent should only access tools granted by the authenticated user's authorization context.

---

# 25. Agent Audit Trail

Important agent operations should produce an audit trail:

```text
Agent
→ Tool
→ Input
→ Authorization
→ Result
→ Decision
→ Action
```

This should allow investigation of unexpected AI behavior.

---

# 26. RAG Architecture

BUILD RAG pipeline:

```text
Source
 ↓
Extraction
 ↓
Chunking
 ↓
Embedding
 ↓
Indexing
 ↓
Hybrid Retrieval
 ↓
Reranking
 ↓
Context Construction
 ↓
LLM
 ↓
Grounded Response
```

Search should combine:

* keyword search;
* semantic search;
* metadata filtering;
* curriculum relationships;
* user context;
* potentially graph relationships.

---

# 27. Academic Search

Search should become an intelligence layer rather than a basic text search.

Example:

> “Find me material on thermodynamics for my MEE 201 course.”

The system should understand:

* user;
* programme;
* course;
* topic;
* curriculum;
* content authority;
* available documents/videos/questions.

---

# 28. AI Memory

Memory must be separated by purpose.

Recommended boundaries:

### Session Memory

Conversation-local context.

### User Learning Memory

Long-term learning preferences, progress, weaknesses, and relevant academic history.

### Academic Memory

Authoritative academic knowledge.

### Agent Operational Memory

Execution-specific state.

These memory types must not be indiscriminately mixed.

---

# 29. AI Hallucination Controls

When sufficient evidence is unavailable, BUILD should:

* say evidence is insufficient;
* ask a clarification question;
* retrieve additional sources;
* defer to an authoritative source;
* or route for human review where appropriate.

AI should not fabricate:

* curriculum requirements;
* official questions;
* university policy;
* lecturer statements;
* examination facts;
* academic regulations.

---

# 30. Content Upload System

BUILD shall provide academic upload interfaces appropriate to each role.

Supported materials may include:

* PDFs;
* lecture notes;
* documents;
* slides;
* images;
* summaries;
* past questions;
* academic videos;
* other approved academic material.

The upload experience should behave conversationally where appropriate.

---

# 31. Upload Assistant

When a user uploads a document, the AI should:

1. inspect it;
2. identify likely academic content;
3. infer metadata;
4. determine course/programme/level/semester where possible;
5. identify source/type;
6. determine whether clarification is required;
7. ask only necessary questions;
8. validate;
9. ingest.

Example:

> “This appears to be CSC 201 lecture material, but I can't confidently determine the semester. Which semester should I associate it with?”

---

# 32. Upload Success Contract

The system should only report:

> **Document ingested successfully.**

after the required ingestion and validation conditions are satisfied.

---

# 33. Duplicate Prevention

Duplicate prevention is a hard system invariant.

Duplicate detection must not depend solely on filename.

Detection should consider:

* exact file hash;
* normalized content hash;
* document/page fingerprints;
* semantic similarity;
* metadata;
* source;
* version information.

The system should distinguish:

```text
Exact Duplicate
Near Duplicate
New Version
Related Document
New Document
```

A legitimate revised document must not be incorrectly rejected as a duplicate.

---

# 34. Content Lifecycle

Academic content should support states such as:

```text
UPLOADED
→ PROCESSING
→ CLASSIFIED
→ VALIDATING
→ INGESTED
→ INDEXED
→ ACTIVE
→ SUPERSEDED
→ ARCHIVED
```

---

# 35. Content Provenance

Every academic knowledge object should record, where applicable:

* source;
* uploader;
* tenant;
* course;
* programme;
* level;
* semester;
* session;
* type;
* provenance;
* version;
* ingestion status;
* verification status;
* curriculum alignment;
* reviewer;
* timestamps.

---

# 36. Content Conflict Resolution

Conflicting content must not be silently merged.

Authority hierarchy should be considered:

1. official university source;
2. authoritative academic administration;
3. official curriculum;
4. approved lecturer material;
5. verified institutional material;
6. contributed material;
7. student material;
8. AI-generated content.

The exact hierarchy may vary by content type.

Conflicting sources should remain preserved as provenance.

---

# 37. OCR

AI service shall support OCR for academic documents.

Initial strategy may use OpenVINO + PaddleOCR.

OCR pipeline should support:

* document images;
* scanned PDFs;
* text extraction;
* layout-aware extraction where feasible;
* tables where supported;
* orientation handling;
* confidence;
* provenance.

OCR output must feed downstream ingestion rather than remaining isolated.

---

# 38. AI Model Gateway

BUILD shall implement a provider-agnostic Model Gateway.

The initial production foundation model shall be:

**Meta Muse Glimmer 30B accessed through Together AI.**

The AI service must not couple:

* agent runtime;
* RAG;
* memory;
* tools;
* business logic;
* evaluation;
* or orchestration

directly to Together or Glimmer-specific APIs.

Gemini and other foundation models shall remain pluggable.

---

# 39. Initial Model Configuration

Conceptually:

```text
MODEL_PROVIDER=together
MODEL_NAME=meta-models/Muse-Glimmer-30B
```

The actual provider configuration should be externalized.

The Model Gateway should handle:

* authentication;
* retries;
* timeouts;
* token budgets;
* structured output;
* tool calling;
* fallback;
* observability;
* cost tracking;
* model selection.

---

# 40. Model Evaluation

BUILD must not assume that one model is universally superior.

The BUILD AI Evaluation Lab should compare models against BUILD-specific evaluations.

Evaluation dimensions include:

* factual accuracy;
* curriculum alignment;
* RAG accuracy;
* citation correctness;
* tool selection;
* tool arguments;
* question quality;
* hallucination;
* latency;
* cost;
* refusal behavior;
* personalization;
* structured output reliability.

Model decisions should be evidence-driven.

---

# 41. AI Cost Governance

AI usage must be measurable by:

* tenant;
* user;
* feature;
* agent;
* model;
* request;
* tokens;
* latency;
* estimated cost.

The platform should support:

* budgets;
* rate limits;
* agent step limits;
* tool limits;
* model limits;
* usage alerts.

---

# 42. Student Progress

Progress should connect learning activities across:

* Read Mode;
* Video Mode;
* CBT Mode;
* AI Tutor;
* study plans.

Examples:

```text
Read completion
Video completion
CBT attempts
Topic mastery
Weak topics
Question accuracy
Study activity
```

---

# 43. Personalization

Full ML personalization is not required for the initial product foundation.

However, the architecture should collect the necessary signals for future personalization.

Potential inputs:

* curriculum;
* progress;
* CBT performance;
* question history;
* weak topics;
* study frequency;
* upcoming assessments;
* available time;
* learning activity.

Future system:

```text
Student State
      ↓
Personalization Engine
      ↓
Recommended
Content / Questions / Study Plan
```

---

# 44. Academic Calendar Intelligence

BUILD should understand academic time.

The system should eventually model:

* session;
* semester;
* registration;
* lectures;
* tests;
* examinations;
* breaks;
* results;
* academic deadlines.

This enables context-aware academic assistance.

---

# 45. Analytics

BUILD analytics should be separated into three categories.

## Product Analytics

* active users;
* sessions;
* feature use;
* retention;
* engagement.

## Academic Analytics

* course performance;
* topic mastery;
* CBT performance;
* question difficulty;
* weak areas.

## System Analytics

* ingestion success;
* duplicate rate;
* AI latency;
* RAG quality;
* errors;
* API performance;
* storage;
* token usage;
* AI cost.

Google Analytics may be used as an owner-level integration but must not become the only analytics system.

---

# 46. Social / Group Chat

BUILD shall support academic collaboration.

Capabilities may include:

* groups;
* group conversations;
* academic discussions;
* course-oriented collaboration;
* study communities.

Moderation, reporting, permissions, and privacy requirements shall apply.

---

# 47. Leaderboard

Leaderboard shall provide gamified academic engagement.

Possible signals:

* CBT activity;
* study activity;
* verified achievements;
* course performance metrics where appropriate.

Leaderboard design must avoid exposing sensitive academic information unnecessarily.

---

# 48. Campus Map

BUILD shall provide a campus intelligence experience.

The initial campus dataset should eventually contain:

* campus boundary;
* roads;
* walkways;
* buildings;
* schools;
* departments;
* lecture halls;
* hostels;
* laboratories;
* libraries;
* clinics;
* cafeterias;
* ATMs;
* landmarks;
* other facilities.

---

# 49. GIS Architecture

PostgreSQL + PostGIS should be used for spatial domain data where appropriate.

Supported geometry may include:

* POINT;
* LINESTRING;
* POLYGON;
* MULTIPOLYGON.

Potential queries:

* nearby facilities;
* locations within campus;
* closest clinic;
* nearby lecture halls;
* distance between locations;
* future walking routes.

---

# 50. Existing FUTA GIS Asset

The current `futa_clip` dataset is a collection of ESRI Shapefile components.

It is treated as a **source/reference GIS layer**, not as the complete campus map.

It should not be consumed directly by React Native.

A GIS processing pipeline should transform appropriate source data into:

* normalized spatial database records;
* GeoJSON;
* vector tiles;
* or another mobile-friendly representation.

---

# 51. Campus Data Acquisition

Additional geographic data must be acquired and validated.

Potential sources:

* official FUTA data;
* OpenStreetMap;
* public GIS data;
* academic datasets;
* satellite/open geographic data;
* existing campus maps;
* manually verified coordinates.

Source provenance must be maintained.

Google Maps should not automatically become BUILD's source of truth.

BUILD should own its FUTA Campus Knowledge Dataset.

---

# 52. Map Product Rollout

## V1

* campus boundary;
* schools;
* departments;
* buildings;
* lecture halls;
* hostels;
* libraries;
* clinics;
* cafeterias;
* landmarks;
* search;
* categories;
* location details;
* current location;
* basic distance.

## V1.5

* walking paths;
* route network;
* estimated walking time.

## V2

* intelligent navigation;
* accessible routes;
* landmark-based directions;
* context-aware AI navigation.

Turn-by-turn navigation should not be the first mapping milestone.

---

# 53. Campus AI Tools

Potential tools:

```text
search_campus_location
get_location_details
find_nearby_locations
find_locations_by_category
calculate_distance
calculate_route
get_campus_information
```

---

# 54. Core Application Navigation

The original navigation concept includes:

```text
Map
Study
Home
Group Chat
Leaderboard
```

The final frontend information architecture may evolve while preserving these major experiences.

---

# 55. Home

Home should serve as the student's academic command center.

Potential content:

* current courses;
* continue learning;
* recent videos;
* recent Read Mode activity;
* CBT recommendations;
* upcoming academic events;
* AI study suggestions;
* progress;
* weak-topic prompts;
* relevant notifications.

---

# 56. Study / Learn

Study is the central learning environment.

It exposes:

```text
Read Mode
Video Mode
CBT Mode
```

These should be connected through the academic knowledge model.

---

# 57. Learning Loop

A student should be able to move naturally:

```text
Read
 ↓
Watch
 ↓
Practise
 ↓
Review
 ↓
Ask AI
 ↓
Identify Weakness
 ↓
Remediate
 ↓
Practise Again
```

This learning loop is more important than treating the modes as separate features.

---

# 58. Upload / Academic Contribution

Student uploads should be useful while remaining governed.

Authorized administrators and owners can upload official academic materials.

Authorized contributors may eventually upload scoped academic content.

Students may upload personal academic materials subject to:

* ownership;
* authorization;
* privacy;
* content policy;
* academic integrity;
* moderation;
* tenant scope.

---

# 59. Authentication

BUILD shall eventually support:

* email authentication;
* Google authentication;
* secure session/token management;
* password reset;
* appropriate verification;
* role-aware access.

Authentication must not use insecure placeholder mechanisms in production.

---

# 60. Authorization

Authorization shall be based on:

```text
Authenticated Account
+
Organization Membership
+
Role
+
Scope
+
Permission
```

Client-supplied headers or IDs must never independently establish authorization.

---

# 61. Backend Responsibilities

The backend is the **system of record and business logic layer**.

It owns:

* identity;
* authentication;
* organizations;
* memberships;
* authorization;
* academic entities;
* curriculum;
* courses;
* questions;
* assessments;
* attempts;
* answers;
* results;
* progress;
* content ownership metadata;
* publication states;
* subscriptions;
* entitlements;
* analytics events;
* business workflows;
* API gateway behavior;
* AI integration boundary.

---

# 62. AI Service Responsibilities

The AI service owns intelligence capabilities including:

* OCR;
* document processing;
* transcript processing;
* embeddings;
* retrieval;
* RAG;
* AI orchestration;
* agent runtime;
* AI tools;
* model gateway;
* memory;
* generation;
* AI evaluation;
* AI guardrails;
* AI observability.

It must not become a second backend.

---

# 63. Frontend Responsibilities

React Native owns:

* presentation;
* navigation;
* learning interfaces;
* video playback;
* CBT interfaces;
* map rendering;
* search UI;
* upload UI;
* chat UI;
* progress visualization;
* interaction state;
* local cache where appropriate.

The frontend must not become the source of truth for business authorization or academic state.

---

# 64. Service Integration

Target architecture:

```text
React Native
      ↓
BUILD Backend
      ↓
AI Service
      ↓
Model Gateway
      ↓
Together / Glimmer
      ↓
Other Providers
```

The backend should remain the principal application gateway.

The AI service should be accessed through controlled service interfaces.

---

# 65. AI Integration Contract

Backend → AI Service communication should support:

* authenticated service requests;
* tenant context;
* user context;
* correlation IDs;
* idempotency keys;
* retries;
* timeouts;
* structured responses;
* callback/event handling where required.

The AI service must not independently trust caller-supplied identity without authenticated service context.

---

# 66. Event Architecture

BUILD should eventually implement domain events such as:

```text
DOCUMENT_UPLOADED
DOCUMENT_INGESTED
DOCUMENT_INDEXED

VIDEO_UPLOADED
VIDEO_PROCESSED
VIDEO_PUBLISHED

COURSE_CREATED
COURSE_UPDATED

QUESTION_CREATED
QUESTION_VERIFIED

CBT_STARTED
CBT_COMPLETED

TOPIC_MASTERED
TOPIC_WEAKNESS_DETECTED

CURRICULUM_UPDATED

USER_JOINED_COURSE

MAP_LOCATION_CREATED
MAP_LOCATION_UPDATED

SUBSCRIPTION_STARTED
SUBSCRIPTION_CHANGED
SUBSCRIPTION_CANCELLED

AI_SESSION_STARTED
AI_SESSION_COMPLETED
```

Events enable:

* analytics;
* notifications;
* memory;
* recommendations;
* audit;
* future personalization.

---

# 67. Database Ownership

The backend and AI service must have explicit data ownership.

The AI service must not recreate backend-owned tables.

Backend-owned concepts include:

* users;
* organizations/tenants;
* memberships;
* courses;
* academic structures;
* questions;
* assessments;
* attempts;
* answers;
* progress;
* content metadata;
* subscription state.

AI-owned concepts may include:

* AI session state;
* AI operational memory;
* embeddings;
* retrieval metadata;
* model interaction records;
* AI-specific processing state.

Ownership must be documented per table.

---

# 68. Database Architecture Migration

The existing AI service contains legacy models that overlap with backend responsibilities.

These include parallel:

* users;
* schools;
* exams;
* exam sessions;
* answer sheets;
* questions.

These should not remain as a second CBT/identity domain.

AI-service database migrations must be restructured so that the AI service does not create backend-owned schemas.

---

# 69. Migration Baseline

AI service should maintain its own Alembic versioning strategy for AI-owned tables.

If physical database sharing is temporarily required, the services must still maintain separate migration version tables and strict ownership boundaries.

The AI service must not use `create_all()` to create shadow backend tables in production.

---

# 70. Backend Migration State

The backend has already established a PostgreSQL-compatible migration path through migration 0017.

The migration architecture should remain authoritative for backend-owned tables.

Fresh PostgreSQL and SQLite environments have been validated through the current migration sequence.

---

# 71. Production Security

Production requirements include:

* real password hashing;
* secure JWT/session implementation;
* strong secrets;
* secure password reset;
* authentication on protected AI endpoints;
* tenant isolation;
* authorization checks;
* rate limiting;
* audit logging;
* secure service authentication;
* safe callback verification;
* secure storage;
* least privilege.

---

# 72. AI Endpoint Security

All protected AI routes must require authenticated and authorized context.

The platform must prevent:

* forged tenant headers;
* caller-supplied identity impersonation;
* IDOR;
* unauthorized document access;
* unauthorized memory access;
* unauthorized academic content access.

---

# 73. Secrets

Production must reject unsafe defaults for:

* JWT secrets;
* service authentication secrets;
* provider API keys;
* database credentials;
* storage credentials.

Secrets must be supplied through secure deployment configuration.

---

# 74. Rate Limiting

Rate limiting must actually be connected to the relevant API paths.

A limiter existing in code but not being applied is not considered a security control.

Rate limits should consider:

* account;
* tenant;
* endpoint;
* AI feature;
* IP where appropriate.

---

# 75. Academic Integrity

BUILD shall distinguish:

* study assistance;
* practice;
* official assessment;
* active examinations.

AI must not facilitate unauthorized cheating in active examinations.

Official assessments require appropriate controls.

---

# 76. Human-in-the-Loop Governance

Human review should be required for high-impact operations such as:

* curriculum changes;
* official question publication;
* answer corrections;
* official academic structure;
* lecturer content where policy requires;
* high-confidence-sensitive academic claims.

Low-risk content may be auto-published when confidence and policy conditions are satisfied.

---

# 77. Confidence System

Extraction and classification systems should provide field-level confidence where practical.

Example:

```text
Course: CSC 201        0.97
Programme: CSC         0.94
Level: 200             0.91
Semester: ?            0.42
```

If semester confidence falls below the configured threshold, BUILD should ask the user.

---

# 78. Subscription Philosophy

BUILD shall follow a:

> **Free-first, student-accessible monetization model.**

The goal is not to place a paywall between students and basic academic learning.

Students should be able to meaningfully use BUILD without paying.

---

# 79. Free Tier

The Free tier should include substantial academic functionality.

Potential free capabilities:

* account;
* academic profile;
* course structure;
* Read Mode;
* meaningful access to learning materials;
* basic Video Mode;
* basic CBT;
* basic progress;
* basic AI explanations;
* academic search;
* groups;
* leaderboard;
* campus map;
* meaningful AI allowance.

The exact allowance should be determined using real usage and cost data.

---

# 80. Premium Tier

Premium should primarily unlock:

* higher AI usage;
* deeper document analysis;
* advanced RAG;
* personalized tutoring;
* advanced study plans;
* advanced weakness analysis;
* adaptive practice;
* deeper analytics;
* advanced agent capabilities;
* priority or advanced models;
* larger processing limits;
* additional convenience features.

Premium should feel like **more intelligence**, not permission to learn.

---

# 81. Future Subscription Levels

The platform may eventually support:

### BUILD Free

Core academic companion.

### BUILD Plus

Affordable student intelligence tier.

### BUILD Pro / Power Student

High-usage advanced AI tier.

---

# 82. Institutional Sponsorship

Students should not be the only potential payer.

BUILD should support institution-sponsored access.

Potential customers include:

* universities;
* faculties;
* departments;
* academic organizations;
* sponsors;
* alumni organizations;
* scholarship programmes.

A university could sponsor premium access for its students.

---

# 83. Sponsored Access

Entitlements may be sponsored by:

* university;
* department;
* company;
* scholarship;
* alumni;
* BUILD campaigns.

A student should not necessarily need to pay personally to access advanced capabilities.

---

# 84. Subscription Architecture

The backend should own:

* plans;
* subscriptions;
* billing state;
* entitlement state;
* usage;
* sponsored access;
* promotional access.

The AI service should consume scoped entitlements.

It must not independently decide whether a student is Premium.

---

# 85. Entitlement System

Conceptual architecture:

```text
Subscription
      ↓
Plan
      ↓
Entitlements
      ↓
Usage
      ↓
Access Decision
```

Example entitlements:

```text
AI_MESSAGES_MONTHLY
DOCUMENT_PROCESSING
VIDEO_PROCESSING
QUESTION_GENERATION
ADVANCED_TUTOR
PERSONALIZED_STUDY_PLAN
ADVANCED_ANALYTICS
PREMIUM_MODEL_ACCESS
STORAGE_LIMIT
```

Limits should be configurable without application-code changes.

---

# 86. Usage Metering

Usage should be measured by:

* student;
* tenant;
* feature;
* model;
* request;
* tokens;
* document;
* video;
* agent execution.

The UI should prefer human-readable usage indicators rather than raw token counts.

---

# 87. Subscription UX

Subscription limits should not feel punitive.

Instead of:

> “You cannot continue. Upgrade.”

BUILD should communicate:

> “You've used your free AI study allowance for this period. Your allowance will reset soon, or you can unlock more AI study capacity with BUILD Plus.”

Core academic access should remain available.

---

# 88. Subscription Rollout

Initial BUILD launch should prioritize:

1. free access;
2. usage metering;
3. cost measurement;
4. student behavior analysis;
5. feature-value analysis;
6. then monetization.

Pricing should be informed by actual usage and student value rather than guessed before launch.

---

# 89. Notifications

BUILD may notify users about:

* upcoming assessments;
* study reminders;
* content availability;
* progress;
* weak areas;
* new videos;
* new questions;
* group activity;
* academic calendar events;
* subscription status;
* AI usage.

Notifications must be configurable and non-abusive.

---

# 90. Storage Architecture

Academic media should use appropriate object/media storage.

The database should store metadata rather than large binary files where appropriate.

Video architecture should support:

* original upload;
* normalized media;
* thumbnails;
* transcripts;
* chapters;
* playback URLs;
* access control.

---

# 91. Video Delivery

Video playback should use an appropriate streaming/delivery architecture rather than serving large raw files directly from the API.

Future support may include:

* adaptive streaming;
* CDN delivery;
* signed URLs;
* access control;
* resume position.

---

# 92. Accessibility

BUILD should support accessibility across:

* text;
* color;
* controls;
* video;
* audio;
* navigation;
* screen readers;
* font sizing;
* interaction patterns.

---

# 93. Offline / Poor Connectivity Strategy

Full offline AI is not an initial requirement.

Future offline capability should prioritize:

* cached curriculum;
* course metadata;
* Read Mode;
* selected learning content;
* selected CBT;
* progress synchronization.

AI features can initially require connectivity.

---

# 94. Observability

BUILD should provide observability across:

### Backend

* requests;
* errors;
* latency;
* database;
* queues;
* events.

### AI

* model latency;
* retrieval;
* tool calls;
* agent steps;
* token usage;
* cost;
* failures;
* hallucination/evaluation metrics.

### Content

* ingestion success;
* OCR quality;
* duplicate rate;
* processing duration.

### Video

* processing success;
* transcription success;
* playback failures.

---

# 95. AI Evaluation Metrics

BUILD should monitor:

* retrieval relevance;
* citation correctness;
* answer correctness;
* hallucination rate;
* tool-call success;
* question validity;
* question duplication;
* document classification accuracy;
* curriculum alignment;
* video alignment;
* latency;
* cost;
* refusal correctness;
* personalization quality.

---

# 96. Testing Strategy

Testing should exist at:

* unit level;
* integration level;
* API level;
* database level;
* AI-service level;
* OCR level;
* RAG level;
* agent level;
* frontend level;
* end-to-end level.

Production readiness requires more than passing unit tests.

---

# 97. AI Evaluation Lab

BUILD shall maintain a repeatable evaluation suite for comparing models and AI implementations.

It should contain representative tasks for:

* tutoring;
* academic retrieval;
* curriculum reasoning;
* document classification;
* question generation;
* answer verification;
* tool use;
* agent planning;
* hallucination resistance;
* citations;
* personalization.

---

# 98. Performance

The platform should establish explicit performance targets for:

* API response time;
* search;
* RAG;
* AI response initiation;
* document ingestion;
* OCR;
* video processing;
* CBT submission;
* map search.

Targets should be measured under realistic load.

---

# 99. Scalability

Architecture should support progression from:

```text
FUTA pilot
   ↓
FUTA production
   ↓
Multiple universities
   ↓
Large multi-tenant platform
```

Scaling mechanisms may include:

* background workers;
* queues;
* caching;
* database indexing;
* horizontal service scaling;
* object storage;
* vector infrastructure;
* model routing.

---

# 100. Existing AI-Service Reconciliation

The current AI service has substantial existing infrastructure, including:

* agent runtime;
* OCR;
* RAG components;
* adapters;
* service boundaries;
* HMAC/callback mechanisms;
* task infrastructure;
* testing.

Existing useful patterns should be preserved where architecturally sound.

The following must not be blindly discarded:

* task worker;
* HMAC mechanisms;
* reciprocal rank fusion;
* InMemoryVectorStore isolation patterns;
* ports/adapters architecture.

They should instead be reconciled with the target architecture.

---

# 101. Existing AI-Service Issues to Resolve

Known architectural issues include:

* production dependency/image configuration;
* migration baseline;
* shared database ownership;
* authentication;
* secrets;
* rate limiting;
* embeddings;
* persistent vector store;
* question persistence;
* knowledge-tree generation;
* OCR wiring;
* observability;
* test coverage gaps;
* agent HTTP wiring.

These are implementation concerns rather than reasons to discard the architecture wholesale.

---

# 102. Existing Backend Reconciliation

The backend should become the authoritative domain system.

Existing placeholder authentication must be replaced with production-grade mechanisms.

Existing migration architecture should remain the backend source of truth.

Existing AI gateway behavior should remain the integration boundary while being hardened.

---

# 103. AI Database Reconciliation

The AI service currently contains legacy identity/CBT structures that conflict with backend architecture.

The final architecture must prevent:

```text
Backend Users
+
AI Users
```

or:

```text
Backend Questions
+
AI Questions
```

from becoming parallel systems.

AI-owned memory and AI operational data should remain distinct.

---

# 104. Migration Philosophy

Migration should be:

* incremental;
* reversible where possible;
* tested;
* documented;
* narrow;
* observable.

No broad destructive reset should be used as a shortcut.

---

# 105. Deployment

Production deployment must support:

* reproducible builds;
* migrations;
* health checks;
* environment configuration;
* secret injection;
* logging;
* rollback;
* database backup;
* monitoring.

Application containers must not depend on development-only schema creation.

---

# 106. CI/CD

CI should verify:

* tests;
* linting;
* typing where configured;
* security checks;
* migration correctness;
* fresh database boot;
* application startup;
* container build;
* relevant AI/OCR smoke tests.

---

# 107. API Design

APIs should be:

* versioned;
* authenticated;
* authorization-aware;
* tenant-aware;
* idempotent where necessary;
* observable;
* documented.

AI endpoints should have explicit contracts rather than raw unstructured model responses.

---

# 108. Structured AI Responses

AI-generated structured outputs should be validated against schemas.

Question generation, classifications, metadata extraction, tool calls, and other machine-consumed AI outputs must not depend solely on free-form text.

---

# 109. Reliability

BUILD should tolerate:

* model failures;
* provider outages;
* transient network errors;
* OCR failures;
* document corruption;
* video processing failures;
* duplicate events;
* retries.

AI should fail gracefully rather than bringing down core academic functionality.

---

# 110. Provider Fallback

The Model Gateway should support future provider fallback.

Possible:

```text
Primary Model
    ↓
Failure / Policy / Budget
    ↓
Fallback Model
```

Fallback must preserve:

* authorization;
* context;
* safety;
* cost limits;
* observability.

---

# 111. Data Privacy

BUILD should apply data minimization.

Sensitive information should only be collected and retained where necessary.

User academic activity should not automatically become visible to other students.

---

# 112. Academic Content Rights

BUILD must respect copyright and licensing.

The platform should prioritize:

* official academic materials;
* lecturer-provided materials;
* institution-provided content;
* appropriately licensed resources;
* open educational resources;
* user-owned contributions.

BUILD should not build its academic corpus by indiscriminately scraping copyrighted commercial textbooks.

---

# 113. Source Hierarchy

Recommended source hierarchy:

## Tier 1

Official academic sources:

* CCMAS;
* FUTA;
* official curriculum;
* official course outlines;
* faculty/department publications.

## Tier 2

Institution-provided materials:

* lecturer notes;
* handouts;
* slides;
* official course PDFs.

## Tier 3

Past questions:

* departmental;
* faculty;
* institutional;
* CBT/examination material where authorized.

## Tier 4

Licensed/open resources.

## Tier 5

Student contributions.

---

# 114. Academic Integrity of Uploaded Material

Uploaded content must have metadata describing:

* source;
* uploader;
* ownership/authorization where required;
* academic context;
* verification status.

The platform should avoid presenting unauthorized material as official.

---

# 115. Product Analytics and AI Analytics Separation

Product usage and AI performance should be analytically distinct.

Example:

A student using AI 100 times is a product usage event.

Whether those 100 answers were accurate is an AI quality metric.

Both matter, but they represent different dimensions.

---

# 116. Security and Audit Trail

Important actions should be auditable.

Examples:

* role changes;
* curriculum changes;
* question publication;
* content approval;
* video publication;
* subscription changes;
* administrative actions;
* AI tool mutations;
* academic verification.

---

# 117. Future Personalization Engine

A future personalization engine may use:

```text
Curriculum
+
Student Profile
+
Learning Progress
+
CBT Results
+
Question History
+
Weak Topics
+
Study Time
+
Upcoming Assessments
+
Learning Activity
```

to produce:

* study plans;
* recommended topics;
* question difficulty;
* remediation;
* revision schedules;
* resource recommendations.

---

# 118. Future Adaptive Learning

BUILD may eventually support adaptive difficulty.

Example:

```text
Student performs poorly
        ↓
Weakness detected
        ↓
Simpler explanation
        ↓
Targeted practice
        ↓
Moderate difficulty
        ↓
Advanced question
```

This should be introduced after sufficient performance data and evaluation.

---

# 119. Future Intelligent Agent

The long-term BUILD AI agent should be capable of coordinating:

* academic search;
* curriculum interpretation;
* content retrieval;
* tutoring;
* study planning;
* CBT;
* progress analysis;
* campus information;
* notifications;
* recommendations.

The agent should remain constrained by permissions and explicit tool boundaries.

---

# 120. System Architecture Summary

```text
                              BUILD
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
        Identity             Academic            Campus
        & Tenancy           Intelligence        Intelligence
             │                  │                  │
             │        ┌─────────┴────────┐         │
             │        │                  │         │
             │    Curriculum          Content      GIS
             │    Pipeline            Pipeline     System
             │        │                  │         │
             └────────┼──────────────────┼─────────┘
                      │
                      ▼
               BACKEND SYSTEM
                  OF RECORD
                      │
                      ▼
              ┌───────────────┐
              │   AI SERVICE  │
              │               │
              │ Agent Runtime │
              │ RAG           │
              │ OCR           │
              │ Memory        │
              │ Tools         │
              │ Evaluation    │
              │ Guardrails    │
              │ Model Gateway │
              └───────┬───────┘
                      │
             ┌────────┴────────┐
             ▼                 ▼
         Glimmer             Gemini
          /Together         /Provider
```

Around all components:

```text
Security
Privacy
Observability
Audit
Governance
Cost Controls
Provenance
Versioning
Events
```

---

# 121. End-to-End Student Experience

A representative BUILD journey:

```text
Student signs in
      ↓
Academic profile established
      ↓
Programme / level / semester
      ↓
BUILD understands curriculum
      ↓
Student selects course
      ↓
Study
 ┌────┼─────┐
 ↓    ↓     ↓
Read Video CBT
 └────┼─────┘
      ↓
AI Tutor
      ↓
Questions
      ↓
Performance
      ↓
Weakness Detection
      ↓
Targeted Remediation
      ↓
Progress
      ↓
Personalized Study
```

---

# 122. Example Multimodal Learning Flow

Student opens:

```text
MEE 201 → Thermodynamics → First Law
```

They can:

### Read

Read structured explanation.

### Watch

Watch associated lecture video.

### Ask

Ask AI to explain a difficult section.

### Practise

Attempt related CBT questions.

### Analyze

BUILD identifies a weakness.

### Remediate

BUILD recommends:

* a relevant section;
* a video chapter;
* an explanation;
* easier questions.

### Reassess

Student attempts another set.

This creates a continuous learning loop.

---

# 123. V1 Scope

V1 should prioritize:

### Identity

* authentication;
* profiles;
* organizations;
* roles;
* permissions.

### Academic

* FUTA structure;
* curriculum;
* courses;
* Read Mode;
* Video Mode;
* CBT.

### AI

* AI Tutor;
* RAG;
* OCR;
* document processing;
* basic agent tools;
* Model Gateway.

### Content

* document upload;
* video upload;
* classification;
* duplicate detection;
* provenance;
* processing.

### Social

* groups;
* leaderboard.

### Campus

* core map;
* campus locations;
* search.

### Analytics

* student progress;
* basic academic analytics;
* system/AI observability.

### Monetization

* free-first;
* entitlement infrastructure;
* usage metering;
* premium architecture.

---

# 124. V1 Explicit Non-Goals

The following should not become uncontrolled V1 scope:

* full offline AI;
* full multi-university rollout;
* advanced ML personalization;
* unrestricted autonomous agents;
* turn-by-turn campus navigation;
* uncontrolled textbook scraping;
* automatic publication of AI-generated official questions;
* complex payment ecosystem before usage data exists.

---

# 125. V1.5

Potential additions:

* richer Video Mode;
* walking routes;
* stronger personalization;
* expanded AI agents;
* richer analytics;
* institution-sponsored subscriptions;
* improved document intelligence;
* expanded academic content.

---

# 126. V2

Potential capabilities:

* multi-university expansion;
* advanced personalization;
* adaptive learning;
* intelligent campus navigation;
* advanced agent workflows;
* sophisticated academic knowledge graph;
* institutional analytics;
* enterprise university licensing;
* deeper multimodal learning.

---

# 127. Risks

Major risks include:

### Academic accuracy

Incorrect academic information can damage trust.

### AI hallucination

Mitigated through retrieval, provenance, evaluation, and uncertainty.

### Content rights

Mitigated through provenance and source governance.

### Cost

Mitigated through usage metering, model routing, budgets, and subscriptions.

### Duplicate content

Mitigated through multi-level duplicate detection.

### Curriculum drift

Mitigated through versioning and curriculum pipeline.

### Tenant isolation

Mitigated through backend authorization and database boundaries.

### AI dependency

Mitigated through Model Gateway.

### Overengineering

Mitigated through staged rollout and explicit V1 scope.

---

# 128. Architectural Constraints

The following are strong constraints:

1. Backend remains system of record.
2. AI service remains intelligence layer.
3. AI must not own identity independently.
4. AI must not create shadow CBT systems.
5. Client must not determine authorization.
6. Model provider must remain replaceable.
7. Academic provenance must be preserved.
8. Curriculum must be versioned.
9. AI-generated academic content must be clearly identified.
10. Core learning should not be paywalled.
11. GIS source data must be normalized before mobile consumption.
12. High-impact academic changes require governance.
13. Production schema must come from migrations.
14. Development shortcuts must not become production architecture.

---

# 129. Definition of Done — Product

BUILD V1 is not considered complete merely because screens exist.

A feature is complete when:

* UX is implemented;
* backend contract exists;
* authorization is enforced;
* data ownership is defined;
* tests exist;
* observability exists;
* failure states exist;
* security has been considered;
* provenance exists where applicable;
* analytics/events are defined;
* documentation exists.

---

# 130. Definition of Done — AI

An AI capability is complete when:

* provider abstraction exists;
* prompts/configuration are versioned;
* structured outputs are validated;
* retrieval is grounded where required;
* permissions are enforced;
* tool calls are audited;
* usage/cost is measured;
* latency is measured;
* evaluation cases exist;
* failure behavior is defined.

---

# 131. Definition of Done — Academic Content

Content is considered active when:

* source is known;
* metadata is validated;
* curriculum alignment is established;
* duplicate status is resolved;
* processing succeeded;
* provenance is stored;
* authorization is established;
* publication state is approved.

---

# 132. Definition of Done — Video

A production academic video should have:

* validated media;
* appropriate metadata;
* course/topic alignment;
* thumbnail;
* playable representation;
* access control;
* processing state;
* transcript where supported;
* chapters where supported;
* provenance;
* publication state.

---

# 133. Definition of Done — CBT

A production question should have:

* source;
* academic alignment;
* answer;
* validation;
* appropriate metadata;
* provenance;
* difficulty where applicable;
* verification state.

Attempts must be persisted transactionally.

---

# 134. Definition of Done — Subscription

Subscription infrastructure is production-ready when:

* plan definitions exist;
* entitlements exist;
* usage is metered;
* access decisions are backend-owned;
* sponsorship is supported architecturally;
* AI respects entitlements;
* limits are configurable;
* billing state is auditable.

---

# 135. Traceability Model

Every major product requirement should map to:

```text
Requirement
   ↓
Domain
   ↓
Service
   ↓
Database Entity
   ↓
API
   ↓
Frontend Experience
   ↓
Tests
   ↓
Observability
```

This prevents features from existing only at UI level.

---

# 136. Engineering Workstream Structure

Implementation should eventually be divided into controlled workstreams:

1. Foundation / Security
2. Identity / Tenancy
3. Academic Catalogue
4. Curriculum Intelligence
5. Content Pipeline
6. Read Mode
7. Video Mode
8. CBT
9. AI Tutor
10. RAG
11. Agent Runtime
12. Model Gateway
13. Memory
14. Progress / Analytics
15. Social
16. Campus GIS
17. Subscription / Entitlements
18. Observability
19. Evaluation
20. Production Infrastructure

Workstreams should be implemented incrementally rather than attempting a single massive rewrite.

---

# 137. Repository Strategy

BUILD should preserve separation between:

```text
ai-service
build-backend
build-frontend
```

The repositories should have explicit service boundaries.

The backend owns domain state.

The AI service owns intelligence.

The frontend owns presentation and interaction.

---

# 138. Engineering Migration Principle

Existing code should be treated as:

**Current State**

while this PRD represents:

**Target State**

The migration path is:

```text
Current Implementation
        ↓
Audit
        ↓
Gap Identification
        ↓
Incremental Migration
        ↓
Verification
        ↓
Target Architecture
```

The existing implementation should not be discarded simply because it differs from the target design.

---

# 139. Current-State Reconciliation Priority

Highest-priority engineering gaps are:

## AI Service

1. Production Docker image.
2. Migration baseline.
3. Database ownership.
4. Authentication.
5. Secrets.
6. Rate limiting.
7. Real embeddings.
8. Persistent vector store.
9. Question persistence.
10. Knowledge-tree intelligence.
11. OCR integration.
12. AI observability.
13. Agent HTTP integration.

## Backend

1. Production authentication.
2. Authorization.
3. Academic catalogue.
4. Curriculum model.
5. Learning/progress model.
6. Content model.
7. Video model.
8. CBT production hardening.
9. Subscription/entitlements.
10. AI integration.
11. Events.
12. Analytics.

---

# 140. Product Success Metrics

BUILD should measure:

### Adoption

* registered students;
* activated students;
* weekly active students;
* monthly active students.

### Learning

* Read Mode completion;
* Video completion;
* CBT attempts;
* topic mastery;
* remediation success.

### AI

* useful responses;
* grounded answer rate;
* retrieval relevance;
* question quality;
* AI latency;
* AI cost/user.

### Content

* uploads;
* ingestion success;
* duplicate rate;
* processing time;
* verified content.

### Retention

* day 1;
* day 7;
* day 30;
* semester retention.

### Monetization

* free → premium conversion;
* sponsored users;
* institutional contracts;
* AI cost per active user;
* subscription retention.

The exact targets should be established after baseline measurements.

---

# 141. Product North Star

The ultimate measure of BUILD should not simply be:

> “How many students opened the application?”

The deeper objective is:

> **How effectively does BUILD help students understand, practise, improve, and succeed academically?**

Usage metrics support this objective; they do not replace it.

---

# 142. Final Product Model

BUILD should ultimately be understood as:

```text
                         BUILD
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
     LEARNING           INTELLIGENCE        CAMPUS
        │                  │                  │
   ┌────┼────┐       ┌─────┼─────┐           │
   │    │    │       │     │     │           │
 Read Video CBT     RAG  Agent  Tutor        GIS
   │    │    │       │     │     │           │
   └────┼────┘       └─────┼─────┘           │
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ACADEMIC GRAPH
                           │
             ┌─────────────┼─────────────┐
             │             │             │
        Curriculum      Content      Performance
             │             │             │
             └─────────────┼─────────────┘
                           │
                    PERSONALIZATION
                           │
                           ▼
                  INTELLIGENT LEARNING
```

---

# 143. Final Architectural Principle

BUILD should not be thought of as:

> “An app with AI features.”

It should be built as:

> **An academic intelligence platform with a student application on top.**

The application is the interface.

The backend is the system of record.

The AI service is the intelligence layer.

The academic knowledge graph is the connective tissue.

The curriculum is the academic foundation.

The content system is the knowledge acquisition mechanism.

The learning modes are the student experience.

The agent system is the orchestration layer.

The Model Gateway makes intelligence replaceable.

The governance layer keeps academic knowledge trustworthy.

The subscription system funds intelligence without unnecessarily restricting learning.

---

# 144. Master Architectural Statement

BUILD shall implement a multi-tenant academic intelligence platform in which the backend serves as the authoritative system of record for identity, tenancy, academic structure, content metadata, assessments, progress, subscriptions, permissions, and business workflows.

The AI service shall provide intelligence capabilities including OCR, retrieval, RAG, agent orchestration, memory, model interaction, academic content enrichment, evaluation, and AI-specific observability without creating shadow versions of backend-owned domains.

BUILD shall provide students with an integrated Learn/Study experience composed of Read Mode, Video Mode, and CBT Mode, all connected through a shared academic knowledge architecture.

BUILD shall treat documents, videos, questions, curriculum, concepts, learning objectives, and student performance as interconnected academic knowledge rather than isolated records.

BUILD shall use a provider-agnostic Model Gateway, with Meta Muse Glimmer 30B through Together AI serving as the initial foundation model while preserving the ability to integrate Gemini and future models.

BUILD shall maintain academic provenance, curriculum versioning, confidence-aware processing, human governance, duplicate prevention, academic integrity controls, and source-aware AI responses.

BUILD shall follow a free-first monetization strategy in which core academic learning remains meaningfully accessible while premium capabilities primarily provide greater intelligence, personalization, capacity, and computationally expensive functionality.

BUILD shall be architected for FUTA first while maintaining the structural ability to expand to additional universities and organizations.

---

# 145. Closing Product Principle

The final product philosophy is:

> **BUILD should make learning more intelligent, not make learning inaccessible.**

Students should come to BUILD because it helps them learn.

They should remain because it understands their academic context.

They should eventually pay only when the additional intelligence, capacity, personalization, or convenience provides enough value to justify doing so.

Institutions should eventually have the ability to sponsor that intelligence for their students.

The technology should remain modular enough that the product can evolve without repeatedly rebuilding its foundations.

---

# 146. Offline AI & Hybrid Intelligence Architecture

## 146.1 Overview

BUILD shall support a **hybrid AI architecture** in which online cloud intelligence and local/offline intelligence coexist as complementary capabilities.

The objective is not to replace cloud AI with a smaller local model. Instead, BUILD shall provide students with useful AI-assisted learning capabilities even when internet connectivity is unavailable, unreliable, expensive, or temporarily interrupted, while retaining access to substantially stronger cloud models whenever connectivity is available.

The architecture shall therefore distinguish between:

1. **Online Intelligence** — cloud and self-hosted models accessed through the BUILD Model Gateway.
2. **Offline Intelligence** — locally available models and educational resources running on the student's device.
3. **Hybrid Intelligence** — coordinated operation between local and online intelligence when connectivity is intermittent or restored.

The local model selection shall remain configurable and shall not be hard-coded into the core application architecture.

## 146.2 Design Principle

BUILD shall optimize for **learning reliability rather than model size**.

A model with more parameters is not automatically a better offline model for BUILD. The usefulness of an offline AI system depends on the combination of:

* model capability;
* educational reasoning ability;
* mathematical correctness;
* course-material grounding;
* retrieval quality;
* hallucination resistance;
* response latency;
* memory consumption;
* storage requirements;
* battery and thermal impact;
* device compatibility;
* runtime stability;
* licensing and redistribution rights;
* and the quality of the surrounding offline intelligence infrastructure.

Therefore, BUILD shall select its offline model configuration through evidence-based benchmarking rather than committing prematurely to a single model.

## 146.3 Local Model Pool

BUILD shall investigate supporting a **pool of compact local language models** rather than assuming that a single model must perform every offline task.

The initial evaluation pool shall include candidates such as:

* Glimmer 2B;
* Qwen3-1.7B;
* Gemma 3 1B;
* SmolLM2-1.7B-Instruct;
* one additional mobile/on-device-oriented candidate selected during technical evaluation.

The exact models used in production shall be determined after benchmarking.

The architecture shall permit:

```text
Local Model Pool
│
├── Model A
├── Model B
├── Model C
├── Model D
└── Model E
```

without requiring the application or AI service architecture to depend on any particular model.

The system may ultimately use:

### Option A — Single best model

One model clearly outperforms the alternatives across BUILD's requirements.

```text
Offline Request
      ↓
Selected Local Model
      ↓
Response
```

### Option B — Task-specialized model routing

Different models demonstrate meaningful strengths in different workloads.

```text
                         Offline Request
                               │
                               ▼
                       Local Model Router
                     ┌─────────┼─────────┐
                     ▼         ▼         ▼
                 Model A    Model B    Model C
                 Math       Summary     General QA
```

### Option C — Multi-model verification

For selected high-value tasks, more than one local model may independently produce or evaluate an answer.

```text
                 Student Question
                       │
              ┌────────┴────────┐
              ▼                 ▼
           Model A           Model B
              │                 │
              └────────┬────────┘
                       ▼
                Verification /
                Consensus Layer
                       │
                       ▼
                 Final Response
```

This mode shall only be used where its additional CPU, RAM, battery, latency, and storage costs are justified.

The system shall **not run all local models simultaneously by default**.

## 146.4 Offline Intelligence Runtime

The offline experience shall not be treated as merely "put a small LLM on the phone."

BUILD shall implement an **Offline Intelligence Runtime** consisting of multiple cooperating components.

```text
Offline Intelligence Runtime
│
├── Local Model Runtime
│     └── Selected compact model(s)
│
├── Local Retrieval
│     ├── Course materials
│     ├── Lecture notes
│     ├── Textbooks/resources
│     └── Academic documents
│
├── Local CBT Knowledge
│     ├── Questions
│     ├── Verified answers
│     └── Explanations
│
├── Deterministic Tools
│     ├── Calculator
│     ├── Mathematical solver
│     └── Other verified utilities
│
├── Local Context Manager
│
├── Confidence/Evidence Evaluation
│
├── Offline Conversation State
│
├── Pending Task Queue
│
└── Synchronization/Reconciliation
```

The purpose of this architecture is to compensate for the reduced general reasoning capability of compact local models by providing them with **high-quality contextual information and deterministic tools**.

## 146.5 Local Course-Material Retrieval

Offline AI shall be capable of answering questions using educational materials that have previously been downloaded, imported, or made available to the student.

Examples include:

* lecture notes;
* course PDFs;
* lecturer-provided materials;
* approved textbooks;
* summaries;
* previously ingested academic documents;
* official course materials;
* and other authorized learning resources.

The system shall locally index appropriate content and retrieve relevant passages before generating an answer.

Example:

```text
Student:
"Explain the concept of hypothesis testing from my MTS 101 notes."

             ↓

Local Retrieval
             ↓
Relevant MTS 101 passages
             ↓
Compact Local Model
             ↓
Grounded explanation
```

The local model should therefore rely on retrieved course evidence whenever appropriate instead of depending entirely on its pretrained knowledge.

This is particularly important for university-specific content where the expected answer may depend on:

* lecturer terminology;
* course-specific definitions;
* institutional curriculum;
* locally provided examples;
* specific formulas;
* or the exact content taught in a course.

## 146.6 Offline CBT Intelligence

BUILD shall provide access to locally available CBT resources when the student is offline.

Where authorized and available, the device may retain:

* CBT questions;
* answer options;
* verified answers;
* explanations;
* topic classifications;
* difficulty levels;
* course associations;
* and other metadata.

Offline CBT functionality may include:

* taking previously downloaded CBTs;
* practicing questions;
* reviewing answers;
* explaining why an answer is correct;
* identifying weak topics;
* generating limited practice variations where reliable;
* and recording progress locally.

Verified question-bank data shall be preferred over model-generated information whenever authoritative content is available.

The local LLM shall not be treated as the source of truth for verified assessment data.

## 146.7 Deterministic Tools

BUILD shall use deterministic computational tools wherever practical instead of requiring a language model to perform calculations that can be verified algorithmically.

Examples include:

* arithmetic;
* algebraic calculations;
* unit conversion;
* statistical calculations;
* numerical evaluation;
* and other supported mathematical operations.

The local model may interpret the student's request and explain the result, while a deterministic engine performs or verifies the calculation.

Example:

```text
Student Question
      ↓
Local Model
      ↓
Identifies mathematical operation
      ↓
Deterministic Solver
      ↓
Verified Result
      ↓
Local Model
      ↓
Step-by-step explanation
```

This architecture is intended to reduce mathematical hallucinations and improve reliability.

## 146.8 Offline Confidence and Evidence Handling

BUILD shall explicitly account for uncertainty in offline responses.

The local system shall distinguish between:

### High-confidence response

The system has sufficient relevant source material and/or deterministic verification.

→ Answer normally.

### Limited-confidence response

The system has some relevant information but insufficient evidence for a highly reliable answer.

→ Answer cautiously and communicate the limitation.

### Low-confidence response

The system lacks sufficient information, encounters conflicting evidence, or cannot reliably solve the problem.

→ Avoid presenting an unsupported answer as fact.

Where appropriate, the student may be offered the ability to save the question for later processing by a stronger online model.

The goal is to ensure that:

> **Offline mode prioritizes trustworthy assistance over confidently generated misinformation.**

## 146.9 Online AI Remains the Primary High-Capability Layer

Offline AI shall **not replace BUILD's online AI infrastructure**.

When connectivity is available, BUILD may access substantially stronger models through the Model Gateway.

The online layer may include:

* commercial model APIs;
* open-weight/self-hosted models;
* cloud inference providers;
* specialized models;
* future model providers;
* and BUILD-hosted inference infrastructure.

Conceptually:

```text
                         BUILD Model Gateway
                                │
                ┌───────────────┴───────────────┐
                │                               │
          Online Intelligence            Offline Intelligence
                │                               │
       ┌────────┼────────┐              ┌───────┴────────┐
       │        │        │              │                │
    Provider A Provider B Provider C   Local Model A   Local Model B
       │        │        │              │                │
       └────────┴────────┘              └───────┬────────┘
                                                │
                                      Local Retrieval/Tools
```

The gateway shall determine the appropriate execution path based on factors such as:

* connectivity;
* task requirements;
* model capability;
* latency;
* cost;
* privacy requirements;
* device capability;
* availability;
* and user/application policy.

## 146.10 Intelligent Model Routing

BUILD shall implement provider- and model-agnostic routing.

The routing system shall not assume that the most powerful available model is always the appropriate model.

Example routing policy:

| Situation                       | Preferred execution             |
| ------------------------------- | ------------------------------- |
| No internet                     | Local intelligence              |
| Very poor connectivity          | Local intelligence              |
| Simple offline explanation      | Local model                     |
| Course-material question        | Local model + local retrieval   |
| Deterministic calculation       | Calculator/solver + local model |
| Normal online academic question | Appropriate cloud model         |
| Complex reasoning               | Stronger cloud model            |
| High-quality generation         | Stronger cloud model            |
| Sensitive local-only task       | Local execution where supported |
| Local model uncertain           | Queue/escalate when permitted   |
| Primary provider unavailable    | Alternate provider              |
| Connectivity restored           | Process eligible queued tasks   |

Routing decisions shall be configurable and should evolve as benchmark and production data become available.

## 146.11 Offline-to-Online Continuity

BUILD shall support continuity between offline and online operation.

The system shall **not synchronize the local model itself with a cloud model**.

Instead, BUILD shall synchronize relevant **work, state, context, and results**.

Example:

```text
                 OFFLINE
                    │
                    ▼
             Student Question
                    │
                    ▼
          Local Intelligence
                    │
              ┌─────┴─────┐
              │           │
          Answer       Needs review
              │           │
              │       Pending Queue
              │           │
              └─────┬─────┘
                    │
              Internet returns
                    │
                    ▼
              Model Gateway
                    │
                    ▼
            Stronger AI model
                    │
                    ▼
            Refined/verified result
                    │
                    ▼
                Student
```

BUILD shall not automatically upload every offline conversation when connectivity returns.

Each queued task shall be subject to defined:

* synchronization rules;
* privacy requirements;
* user consent/policy;
* data-retention rules;
* task priority;
* context requirements;
* and retry behavior.

## 146.12 Offline Task Queue

Tasks that cannot be reliably completed offline may be stored in a local pending queue.

Examples:

* difficult unanswered questions;
* requests requiring a cloud model;
* requests requiring unavailable external knowledge;
* requests flagged for additional verification;
* and other explicitly deferred operations.

Each queued task should retain only the information necessary to resume processing, subject to BUILD's privacy and data-retention policies.

When connectivity returns, the Model Gateway may determine whether the task should:

1. remain local;
2. be processed by a cloud model;
3. be processed by a self-hosted model;
4. be sent to an alternative provider;
5. or be discarded/expired.

## 146.13 Local Model Benchmarking

Before selecting the production offline configuration, BUILD shall conduct a controlled comparative benchmark.

The benchmark shall evaluate candidate models against BUILD-specific workloads rather than relying solely on general-purpose public benchmarks.

Initial evaluation categories shall include:

### Academic reasoning

* university-level conceptual questions;
* multi-step reasoning;
* explanation quality;
* instruction following.

### Mathematics

* arithmetic;
* algebra;
* statistics;
* probability;
* step-by-step solutions;
* correctness and consistency.

### Course-material grounding

* question answering from supplied material;
* retrieval-grounded explanations;
* multi-section synthesis;
* resistance to information not present in the supplied material.

### Hallucination and uncertainty

* unsupported questions;
* insufficient context;
* ambiguous questions;
* conflicting source material;
* willingness to acknowledge uncertainty.

### CBT

* question answering;
* answer explanations;
* distractor analysis;
* practice-question generation where appropriate.

### General academic assistance

* summarization;
* study assistance;
* rewriting;
* classification;
* straightforward conversation.

## 146.14 Real-Device Benchmarking

Model evaluation shall not be limited to developer laptops.

Candidate models shall be tested on representative Android devices, including lower-end devices within BUILD's intended support range.

Metrics shall include:

* first-token latency;
* total response latency;
* tokens/second;
* peak RAM usage;
* persistent storage requirements;
* model download size;
* startup time;
* battery consumption;
* thermal behaviour;
* crash/stability rate;
* concurrent application impact;
* offline runtime compatibility;
* and user-perceived responsiveness.

A model that produces better answers but makes BUILD unusably slow on supported devices may not be selected as the default.

## 146.15 Complete Offline-System Benchmark

BUILD shall evaluate not only raw model performance but complete configurations.

For example:

```text
Configuration A
Model A + Retrieval

Configuration B
Model B + Retrieval

Configuration C
Model C + Retrieval + Calculator

Configuration D
Model D + Retrieval + CBT Bank

Configuration E
Multiple local models + Router + Verification
```

This is important because the best individual model may not produce the best complete offline learning experience.

The final benchmark shall therefore measure:

> **Model capability + context quality + tools + retrieval + device performance + reliability.**

## 146.16 Model Selection Criteria

The production local model configuration shall be selected using a weighted BUILD-specific evaluation.

Indicative criteria may include:

| Criterion                  | Indicative importance |
| -------------------------- | --------------------: |
| Educational correctness    |                   25% |
| Course-material grounding  |                   20% |
| Mathematical correctness   |                   15% |
| Hallucination resistance   |                   10% |
| Explanation quality        |                   10% |
| Latency                    |                    5% |
| RAM requirements           |                    5% |
| Storage requirements       |                    3% |
| Battery/thermal efficiency |                    3% |
| Runtime stability          |                    2% |

These weights are provisional and shall be finalized during the benchmark design.

**Licensing and commercial deployment compatibility shall be treated as a mandatory gate rather than merely a numerical score.**

A model that cannot legally be distributed or deployed under BUILD's intended commercial model shall not be selected regardless of benchmark performance.

## 146.17 Model Gateway Abstraction

The BUILD Model Gateway shall remain independent of the selected local model.

The application shall communicate with an abstract model capability rather than directly targeting a specific model vendor or model name.

Conceptually:

```text
Application
     │
     ▼
Model Gateway
     │
     ├── Local Provider
     │      ├── Model A
     │      ├── Model B
     │      └── Model C
     │
     ├── Cloud Provider A
     ├── Cloud Provider B
     ├── Cloud Provider C
     │
     └── Self-hosted Provider
```

This allows BUILD to:

* replace local models;
* add new models;
* change cloud providers;
* introduce self-hosted inference;
* combine multiple providers;
* perform A/B testing;
* and modify routing policies

without requiring fundamental changes to the student application.

## 146.18 Privacy and Data Handling

Offline processing shall provide an important privacy advantage because some student interactions can be processed entirely on-device without transmitting the underlying content to external providers.

BUILD shall distinguish between:

### Local-only data

Information that remains on-device unless explicitly synchronized according to policy.

### Cloud-eligible data

Information that may be transmitted to an online provider when required and permitted.

### Cloud-required data

Operations that cannot reasonably be completed offline.

The system shall not automatically transmit offline conversations, uploaded academic materials, or other potentially sensitive student data merely because connectivity has returned.

Synchronization shall follow BUILD's privacy, authorization, retention, and consent requirements.

## 146.19 Resource Management

Because mobile devices have limited resources, BUILD shall dynamically manage local AI workloads.

The runtime should consider:

* available RAM;
* battery level;
* thermal state;
* device performance class;
* available storage;
* current application workload;
* model loading cost;
* and connectivity state.

Possible behaviour includes:

```text
High device resources
→ use stronger local model

Limited resources
→ use smaller model

Low battery
→ reduce local inference workload

High thermal pressure
→ reduce inference intensity

No storage
→ prevent additional model/material downloads

Internet available
→ consider cloud execution
```

The local runtime shall not unnecessarily keep multiple large models resident in memory simultaneously.

## 146.20 Progressive Model Availability

BUILD may support downloading additional local models according to device capability and user needs.

For example:

```text
Base Offline Package
├── smallest supported model
├── core retrieval engine
├── essential CBT content
└── core academic tools

Optional Intelligence Pack
├── stronger local model
├── additional subject resources
└── additional capabilities
```

This allows BUILD to support a wider range of Android hardware without forcing every student to download the largest available model.

## 146.21 Architecture Invariant

The following architectural invariant shall be maintained:

> **BUILD must never depend on a single AI model, provider, or inference location for core learning functionality.**

The platform must be capable of operating across:

```text
Cloud AI
      ↕
Self-hosted AI
      ↕
Local AI
      ↕
Deterministic educational tools
      ↕
Verified academic knowledge
```

The system should degrade gracefully as capabilities become unavailable.

## 146.22 Expected Outcome

The desired end state is not simply "BUILD works offline."

The desired end state is:

> **BUILD remains useful, grounded, and trustworthy across a spectrum of connectivity and device conditions.**

A student with a strong internet connection may receive assistance from BUILD's strongest available cloud models.

A student with intermittent connectivity may continue learning through local models, retrieved course materials, CBT resources, and deterministic tools.

A student with no connectivity may still receive meaningful academic assistance from the Offline Intelligence Runtime.

When connectivity returns, BUILD can selectively escalate unresolved or high-value tasks to stronger online intelligence.

This creates a **hybrid educational intelligence system** in which local and cloud AI complement each other rather than compete.

## 146.23 Initial Implementation Direction

The implementation shall proceed in the following order:

1. Define the Offline Intelligence Runtime interfaces.
2. Define the Model Gateway local-provider abstraction.
3. Establish the candidate-model benchmark suite.
4. Benchmark the initial local model candidates.
5. Benchmark candidates on representative Android hardware.
6. Prototype local retrieval over downloaded academic materials.
7. Integrate deterministic mathematical tooling.
8. Prototype local CBT access and verification.
9. Implement confidence/evidence handling.
10. Implement offline task queuing.
11. Implement controlled offline-to-online synchronization.
12. Evaluate single-model versus multi-model local routing.
13. Select the production local configuration based on evidence.
14. Integrate the selected configuration into BUILD without coupling the core architecture to that model.
15. Continue monitoring model and runtime performance as new models become available.

### Decision Status

**Architecture: Approved direction**

**Production local model: Not yet selected**

**Initial candidates: Under evaluation**

**Cloud AI: Remains part of the core architecture**

**Model Gateway: Provider/model agnostic**

**Offline strategy: Local Model Pool + Local RAG + Verified CBT Knowledge + Deterministic Tools + Confidence Handling**

**Final local configuration: Determined by benchmark and real-device validation**

---

# 147. Document Status

This document represents the consolidated target-state product and architecture direction for BUILD.

Before implementation, each requirement should be converted into:

* epics;
* domain requirements;
* API contracts;
* data models;
* acceptance criteria;
* test requirements;
* migration tasks;
* observability requirements;
* and implementation milestones.

The existing repositories should then be audited against this document to produce the definitive:

```text
Current State → Gap → Migration → Target State
```

implementation plan.

---

**End of Master PRD — V2.0**
