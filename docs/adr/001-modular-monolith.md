# ADR 001: Modular Monolith

## Status
Accepted

## Context
The backend needs a maintainable structure without premature service decomposition.

## Decision
We will use a modular monolith architecture with clear domain boundaries and internal events.

## Consequences
This keeps deployment simple while preserving future extraction options.
