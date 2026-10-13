from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from app.events.base import DomainEvent


class SourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class SnapshotStatus(StrEnum):
    CAPTURED = "captured"
    FAILED = "failed"


@dataclass
class CurriculumSnapshot:
    id: str
    source_id: str
    source_url: str
    retrieved_at: datetime
    content_sha256: str
    raw_artifact_uri: str
    parser_version: str
    status: SnapshotStatus = SnapshotStatus.CAPTURED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        source_id: str,
        source_url: str,
        content_sha256: str,
        raw_artifact_uri: str,
        parser_version: str,
        retrieved_at: datetime | None = None,
        snapshot_id: str | None = None,
    ) -> CurriculumSnapshot:
        if not source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not source_url.strip():
            raise ValueError("source_url cannot be empty")
        if not content_sha256.strip() or len(content_sha256) != 64:
            raise ValueError("content_sha256 must be a valid 64-character hex string")
        if not raw_artifact_uri.strip():
            raise ValueError("raw_artifact_uri cannot be empty")
        if not parser_version.strip():
            raise ValueError("parser_version cannot be empty")

        now = datetime.now(timezone.utc)
        return cls(
            id=snapshot_id or str(uuid4()),
            source_id=source_id,
            source_url=source_url,
            retrieved_at=retrieved_at or now,
            content_sha256=content_sha256.lower(),
            raw_artifact_uri=raw_artifact_uri,
            parser_version=parser_version,
            status=SnapshotStatus.CAPTURED,
            created_at=now,
        )


@dataclass
class CurriculumSource:
    id: str
    code: str
    name: str
    base_url: str
    source_type: str
    status: SourceStatus = SourceStatus.ACTIVE
    sync_frequency_days: int = 30
    parser_version: str = "v1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        base_url: str,
        source_type: str = "official_benchmark",
        sync_frequency_days: int = 30,
        parser_version: str = "v1.0",
        source_id: str | None = None,
    ) -> CurriculumSource:
        clean_code = code.strip().upper()
        if not clean_code:
            raise ValueError("source code cannot be empty")
        if not name.strip():
            raise ValueError("source name cannot be empty")
        if not base_url.strip():
            raise ValueError("source base_url cannot be empty")
        if sync_frequency_days < 1:
            raise ValueError("sync_frequency_days must be at least 1")

        now = datetime.now(timezone.utc)
        source = cls(
            id=source_id or str(uuid4()),
            code=clean_code,
            name=name.strip(),
            base_url=base_url.strip(),
            source_type=source_type.strip(),
            status=SourceStatus.ACTIVE,
            sync_frequency_days=sync_frequency_days,
            parser_version=parser_version.strip(),
            created_at=now,
            updated_at=now,
        )
        source._events.append(
            DomainEvent(
                event_type="curriculum.source_created",
                payload={
                    "source_id": source.id,
                    "code": source.code,
                    "name": source.name,
                },
            )
        )
        return source

    def disable(self) -> None:
        if self.status == SourceStatus.DISABLED:
            return
        self.status = SourceStatus.DISABLED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.source_disabled",
                payload={"source_id": self.id, "code": self.code},
            )
        )

    def enable(self) -> None:
        if self.status == SourceStatus.ACTIVE:
            return
        self.status = SourceStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.source_enabled",
                payload={"source_id": self.id, "code": self.code},
            )
        )

    def create_snapshot(
        self,
        source_url: str,
        content_sha256: str,
        raw_artifact_uri: str,
        parser_version: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> CurriculumSnapshot:
        if self.status != SourceStatus.ACTIVE:
            raise ValueError("cannot create snapshot for a disabled curriculum source")

        snapshot = CurriculumSnapshot.create(
            source_id=self.id,
            source_url=source_url,
            content_sha256=content_sha256,
            raw_artifact_uri=raw_artifact_uri,
            parser_version=parser_version or self.parser_version,
            retrieved_at=retrieved_at,
        )
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.snapshot_captured",
                payload={
                    "snapshot_id": snapshot.id,
                    "source_id": self.id,
                    "content_sha256": snapshot.content_sha256,
                    "parser_version": snapshot.parser_version,
                },
            )
        )
        return snapshot

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
