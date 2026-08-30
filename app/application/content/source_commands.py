from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)


@dataclass(slots=True)
class RegisterContentSourceCommand:
    code: str
    name: str
    source_type: ContentSourceType | str
    authority_level: AuthorityLevel | str
    visibility: VisibilityScope | str
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


@dataclass(slots=True)
class UpdateContentSourceCommand:
    source_id: str
    name: str | None = None
    description: str | None = None
    author_name: str | None = None
    publisher: str | None = None
    isbn_or_doi: str | None = None
    source_url: str | None = None
    trust_policy: dict[str, Any] | None = None


@dataclass(slots=True)
class DeprecateContentSourceCommand:
    source_id: str
    reason: str


@dataclass(slots=True)
class RevokeContentSourceCommand:
    source_id: str
    reason: str


@dataclass(slots=True)
class ActivateContentSourceCommand:
    source_id: str


@dataclass(slots=True)
class GetContentSourceQuery:
    source_id: str


@dataclass(slots=True)
class ListContentSourcesQuery:
    tenant_id: str | None = None
    source_type: ContentSourceType | str | None = None
    authority_level: AuthorityLevel | str | None = None
    status: SourceStatus | str | None = None
    include_platform: bool = True
    limit: int = 50
    offset: int = 0
