from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.events.base import DomainEvent


@dataclass
class ContentSource:
    id: str
    code: str
    name: str
    source_type: ContentSourceType
    authority_level: AuthorityLevel
    visibility: VisibilityScope
    status: SourceStatus
    created_by: str
    created_by_email: str
    tenant_id: str | None = None
    faculty_id: str | None = None
    department_id: str | None = None
    programme_id: str | None = None
    description: str | None = None
    author_name: str | None = None
    publisher: str | None = None
    isbn_or_doi: str | None = None
    source_url: str | None = None
    trust_policy: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        source_type: ContentSourceType | str,
        authority_level: AuthorityLevel | str,
        visibility: VisibilityScope | str,
        created_by: str,
        created_by_email: str,
        tenant_id: str | None = None,
        faculty_id: str | None = None,
        department_id: str | None = None,
        programme_id: str | None = None,
        description: str | None = None,
        author_name: str | None = None,
        publisher: str | None = None,
        isbn_or_doi: str | None = None,
        source_url: str | None = None,
        trust_policy: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> ContentSource:
        clean_code = code.strip().upper()
        if not clean_code:
            raise ValueError("source code cannot be empty")
        if not name.strip():
            raise ValueError("source name cannot be empty")
        if not created_by.strip():
            raise ValueError("created_by cannot be empty")
        if not created_by_email.strip():
            raise ValueError("created_by_email cannot be empty")

        st = (
            ContentSourceType(source_type)
            if isinstance(source_type, str)
            else source_type
        )
        al = (
            AuthorityLevel(authority_level)
            if isinstance(authority_level, str)
            else authority_level
        )
        vis = VisibilityScope(visibility) if isinstance(visibility, str) else visibility

        # Invariant 1: Regulatory authority requires platform visibility and no tenant scoping
        if al == AuthorityLevel.REGULATORY:
            if vis != VisibilityScope.PLATFORM:
                raise ValueError(
                    "regulatory content sources must have platform visibility"
                )
            if tenant_id is not None:
                raise ValueError(
                    "regulatory content sources cannot be scoped to a single tenant"
                )

        # Invariant 2: Non-platform visibility scopes require tenant_id
        if vis != VisibilityScope.PLATFORM and not tenant_id:
            raise ValueError(
                f"visibility scope '{vis.value}' requires a valid tenant_id"
            )

        # Invariant 3: Specific sub-tenant visibility requirements
        if vis == VisibilityScope.FACULTY and not faculty_id:
            raise ValueError("faculty visibility scope requires faculty_id")
        if vis == VisibilityScope.DEPARTMENT and not department_id:
            raise ValueError("department visibility scope requires department_id")
        if vis == VisibilityScope.PROGRAMME and not programme_id:
            raise ValueError("programme visibility scope requires programme_id")

        # Invariant 4: Institutional authority requires institutional tenant association
        if al == AuthorityLevel.INSTITUTIONAL and vis == VisibilityScope.PLATFORM:
            raise ValueError(
                "institutional content sources cannot have platform-wide visibility"
            )

        now = datetime.now(timezone.utc)
        source = cls(
            id=source_id or f"csrc-{uuid4()}",
            code=clean_code,
            name=name.strip(),
            source_type=st,
            authority_level=al,
            visibility=vis,
            status=SourceStatus.ACTIVE,
            created_by=created_by.strip(),
            created_by_email=created_by_email.strip(),
            tenant_id=tenant_id.strip() if tenant_id else None,
            faculty_id=faculty_id.strip() if faculty_id else None,
            department_id=department_id.strip() if department_id else None,
            programme_id=programme_id.strip() if programme_id else None,
            description=description.strip() if description else None,
            author_name=author_name.strip() if author_name else None,
            publisher=publisher.strip() if publisher else None,
            isbn_or_doi=isbn_or_doi.strip() if isbn_or_doi else None,
            source_url=source_url.strip() if source_url else None,
            trust_policy=dict(trust_policy) if trust_policy is not None else {},
            created_at=now,
            updated_at=now,
        )

        source._events.append(
            DomainEvent(
                event_type="content.source_created",
                payload={
                    "source_id": source.id,
                    "code": source.code,
                    "name": source.name,
                    "source_type": source.source_type.value,
                    "authority_level": source.authority_level.value,
                    "visibility": source.visibility.value,
                    "tenant_id": source.tenant_id,
                },
            )
        )
        return source

    def update_metadata(
        self,
        name: str | None = None,
        description: str | None = None,
        author_name: str | None = None,
        publisher: str | None = None,
        isbn_or_doi: str | None = None,
        source_url: str | None = None,
        trust_policy: dict[str, Any] | None = None,
    ) -> None:
        if self.status == SourceStatus.REVOKED:
            raise ValueError("cannot update metadata of a revoked content source")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("source name cannot be empty")
            self.name = clean_name

        if description is not None:
            self.description = description.strip() if description else None
        if author_name is not None:
            self.author_name = author_name.strip() if author_name else None
        if publisher is not None:
            self.publisher = publisher.strip() if publisher else None
        if isbn_or_doi is not None:
            self.isbn_or_doi = isbn_or_doi.strip() if isbn_or_doi else None
        if source_url is not None:
            self.source_url = source_url.strip() if source_url else None
        if trust_policy is not None:
            self.trust_policy = dict(trust_policy)

        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.source_updated",
                payload={
                    "source_id": self.id,
                    "code": self.code,
                    "name": self.name,
                },
            )
        )

    def deprecate(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("deprecation reason cannot be empty")
        if self.status == SourceStatus.REVOKED:
            raise ValueError("cannot deprecate a revoked content source")
        if self.status == SourceStatus.DEPRECATED:
            return

        self.status = SourceStatus.DEPRECATED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.source_deprecated",
                payload={
                    "source_id": self.id,
                    "code": self.code,
                    "reason": reason.strip(),
                },
            )
        )

    def revoke(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("revocation reason cannot be empty")
        if self.status == SourceStatus.REVOKED:
            return

        self.status = SourceStatus.REVOKED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.source_revoked",
                payload={
                    "source_id": self.id,
                    "code": self.code,
                    "reason": reason.strip(),
                },
            )
        )

    def activate(self) -> None:
        if self.status == SourceStatus.ACTIVE:
            return

        self.status = SourceStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.source_activated",
                payload={
                    "source_id": self.id,
                    "code": self.code,
                },
            )
        )

    def is_accessible_by(
        self,
        tenant_id: str | None = None,
        faculty_id: str | None = None,
        department_id: str | None = None,
        programme_id: str | None = None,
    ) -> bool:
        """Determines if this content source is accessible within a requested tenant & organizational scope."""
        if self.status == SourceStatus.REVOKED:
            return False

        if self.visibility == VisibilityScope.PLATFORM:
            return True

        if not tenant_id or self.tenant_id != tenant_id:
            return False

        if self.visibility == VisibilityScope.TENANT:
            return True
        if self.visibility == VisibilityScope.FACULTY:
            return self.faculty_id is None or self.faculty_id == faculty_id
        if self.visibility == VisibilityScope.DEPARTMENT:
            return self.department_id is None or self.department_id == department_id
        if self.visibility == VisibilityScope.PROGRAMME:
            return self.programme_id is None or self.programme_id == programme_id
        if self.visibility == VisibilityScope.COURSE_ONLY:
            return True

        return False

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
