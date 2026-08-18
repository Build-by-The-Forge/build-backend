# Identity Contract

## Ownership

- Identity owns users, authentication, sessions, and access control.
- It is the canonical source of truth for user identity.

## Public IDs

- `User.id` is the internal UUID.
- `User.email` and `User.username` are external identifiers.
- JWT tokens carry stable subject claims.

## APIs

Identity APIs should expose:
- `POST /identity/users`
- `POST /identity/authenticate`
- `POST /identity/refresh`
- `GET /identity/me`

## Events

Identity publishes events such as:
- `user.registered`
- `user.authenticated`
- `session.created`
- `session.revoked`

## Service boundaries

- Other layers consume identity for authorization and audit.
- Identity manages password hashing, token issuance, and session lifecycle.
