# ADR 006: Multi-Tenancy

## Status
Accepted

## Context
The platform should be able to support tenant-aware operations from the start.

## Decision
Request handling will include tenant context and correlation identifiers from the foundation layer.

## Consequences
This supports future multi-tenant expansion without invasive refactoring.
