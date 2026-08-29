# ADR 005: AI Service Boundary

## Status
Accepted

## Context
The backend should not own AI-specific business logic.

## Decision
AI responsibilities will live in a separate service boundary and be accessed via an abstraction.

## Consequences
This keeps the backend focused on core application behavior.
