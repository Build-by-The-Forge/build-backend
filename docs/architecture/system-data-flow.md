# System Data Flow

This document describes how data moves through BUILD.
It complements the academic knowledge model by focusing on flow and ownership instead of structure.

## Overview

BUILD is a multi-layer platform.
Each layer owns a different type of truth.

- `Identity` owns user and session identity.
- `Tenant` owns institutional structure.
- `Catalogue` owns academic truth.
- `Academic Content` owns learning resources.
- `AI Service` owns semantic modeling and retrieval.
- `CBT` owns assessment generation and evaluation.

## High-level flow

```
Administrator
      │
      ▼
Curriculum Import
      │
      ▼
Catalogue
      │
      ▼
Academic Content
      │
      ▼
OCR Pipeline
      │
      ▼
Cleaning
      │
      ▼
Chunking
      │
      ▼
Embeddings
      │
      ▼
Vector Store
      │
      ▼
AI Service
      │
 ┌────┴─────┐
 ▼          ▼
Read Mode   CBT
```

## Flow stages

### 1. Curriculum Import

Raw curriculum input arrives from NUC CCMAS or manual admin import.
The import process populates the `Catalogue` with courses, curricula, topics, and outcomes.

### 2. Catalogue

The catalogue captures academic truth:
- what courses exist
- how programmes consume courses
- which topics and learning outcomes are official

The catalogue is intentionally separate from learning content.

### 3. Academic Content

Academic content is the collection of materials that students consume.
This includes books, videos, slides, PDFs, and other pedagogical resources.

Content is mapped to catalogue entities, but it is not owned by the catalogue.

### 4. OCR Pipeline

Documents and learning assets are converted into text through OCR.
This is a content-layer process, not a catalogue process.

### 5. Cleaning

Extracted text is cleaned, normalized, and prepared for chunking.
This stage produces material that can be used for semantic retrieval.

### 6. Chunking

Cleaned content is split into smaller chunks for embedding and search.
Chunks continue to belong to Academic Content.

### 7. Embeddings

Chunks are transformed into embeddings and stored in a vector store.
This is the boundary to the AI service.

### 8. AI Service

The AI service uses catalogue metadata and content embeddings to provide semantic understanding.
It does not own the canonical course or curriculum definitions.

### 9. Read Mode / CBT

The final consumer-facing experiences are built on top of the AI service:
- Read Mode for study and exploration
- CBT for assessment and progress

## Contract boundaries

This flow makes ownership explicit.
The system data flow document should be updated whenever a new layer or pipeline step is added.
