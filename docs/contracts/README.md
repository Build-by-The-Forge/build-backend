# Contracts Overview

The `docs/contracts/` folder defines stable service and data contracts between BUILD bounded contexts.
These contract files are not implementation details; they are the architecture-level agreement between modules.

## Purpose

- Make boundaries explicit
- Record ownership of entities and messages
- Align API consumers and producers
- Reduce coupling across modules
- Support future interfaces and integration work

## Files

- `catalogue-contract.md` — contract for the Academic Catalogue bounded context
- `content-contract.md` — contract for the Academic Content bounded context
- `ai-contract.md` — contract for the AI Service and semantic layer
- `identity-contract.md` — contract for the Identity bounded context
- `events-contract.md` — contract for platform event semantics

## How to use these contracts

1. Read the contract before changing or extending a bounded context.
2. Add or update a contract when a new public API, event, or shared entity is introduced.
3. Keep the contract language implementation-agnostic.
4. Use the contract as the basis for API design, service boundaries, and integration tests.

## Adding a new contract

If a new bounded context appears, create a new contract file in this folder and update `docs/architecture.md`.

## Contract lifecycle

- Contracts should be versioned by architecture milestone, not by code release.
- A contract update is an architectural event and may require review.
- Keep contract documents small and focused on the shared surface area.
