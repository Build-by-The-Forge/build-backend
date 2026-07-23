# ADR 002: Clean Architecture

## Status
Accepted

## Context
Business logic should remain independent from framework and infrastructure concerns.

## Decision
We will separate API, application, domain, and infrastructure layers.

## Consequences
This improves testability and future refactoring.
