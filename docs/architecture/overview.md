# System Architecture

The backend is organized as a modular monolith with clear separation between API, application, domain, and infrastructure concerns.

- API layer: routers and request/response handling
- Application layer: use cases and orchestration
- Domain layer: business entities and rules
- Infrastructure layer: persistence, external services, and integrations

## Academic Knowledge Model

The academic catalogue is modeled in `docs/architecture/academic-knowledge-model.md`.
This document defines the canonical BUILD v0.4.0 catalogue aggregates, schema recommendations, and the boundary between Catalogue and Content.

## System Data Flow

The platform data flow is documented in `docs/architecture/system-data-flow.md`.
That document describes how data moves from curriculum import through catalogue, content, AI, and CBT.

## Platform Contracts

Stable service contracts are documented in `docs/contracts/`.
These files define ownership, public IDs, APIs, and event semantics for catalogue, content, AI, identity, and events.

## Academic Data Strategy

The platform's data authority and curriculum source hierarchy are documented in `docs/vision/academic-data-strategy.md`.
That document defines what BUILD treats as canonical academic truth and what belongs only to supplementary content.

## Domain Map

The v0.4.0 domain model is documented in `docs/domain-map.md`.
This document captures the frozen academic knowledge entity graph and public ID strategy before implementation begins.

## Architectural Decisions

Platform decisions are recorded in `docs/decisions/`.
These ADRs capture governance such as source-of-truth rules and contract boundaries.
