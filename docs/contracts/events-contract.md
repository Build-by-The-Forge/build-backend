# Events Contract

## Purpose

This contract defines the stable events published by the platform and the minimum payload each event carries.

## Event ownership

- Catalogue publishes academic events.
- Content publishes ingestion and asset lifecycle events.
- AI publishes semantic and retrieval events.
- Identity publishes authentication and session events.

## Common event fields

Every event should include:
- `event_id`
- `event_type`
- `timestamp`
- `source`
- `payload`

## Example events

- `course.created`
- `curriculum_version.created`
- `content.asset.ingested`
- `ai.embedding.created`
- `user.registered`
- `session.revoked`

## Versioning

- Events should be versioned when payloads change.
- Consumers should support backward-compatible payload extensions.

## Service boundaries

- Publishers own the schema for their events.
- Consumers contract to the published event shape.
- Event contracts should be documented before the event is used across repositories.
