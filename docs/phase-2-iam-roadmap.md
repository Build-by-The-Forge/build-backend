# Phase 2: Identity & Access Management (IAM)

## Goal

Build the first business bounded context on top of the completed foundation.

## Scope

### Identity
- User registration
- Login and logout
- Refresh tokens and sessions
- Email verification
- Password reset
- Device sessions

### Authorization
- RBAC
- Permission matrix
- Policy enforcement
- Route guards

### Multi-tenancy
- School onboarding
- Faculty
- Department
- Programme
- Academic session
- Semester

### Academic membership
- Student profile
- Lecturer profile
- Membership lifecycle

## Recommended architecture

1. Architecture: define aggregates, entities, and value objects
2. Domain: implement business rules independent of infrastructure
3. Infrastructure: repositories, persistence, and integrations
4. Application: use cases and orchestration
5. API: request/response contracts and endpoints
6. Tests: unit, integration, and contract tests
7. Review: ensure CI remains green before merge
