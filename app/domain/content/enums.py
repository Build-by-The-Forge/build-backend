from __future__ import annotations

from enum import StrEnum


class ContentSourceType(StrEnum):
    CCMAS = "ccmas"
    TEXTBOOK = "textbook"
    LECTURER_UPLOAD = "lecturer_upload"
    ADMIN_UPLOAD = "admin_upload"
    COURSE_MATERIAL = "course_material"
    WEB_SOURCE = "web_source"


class AuthorityLevel(StrEnum):
    REGULATORY = "regulatory"
    INSTITUTIONAL = "institutional"
    APPROVED_REFERENCE = "approved_reference"
    EXTERNAL = "external"
    USER_PROVIDED = "user_provided"
    AI_DERIVED = "ai_derived"

    @property
    def rank(self) -> int:
        """Lower numerical value indicates higher baseline regulatory/institutional authority."""
        ranks = {
            AuthorityLevel.REGULATORY: 1,
            AuthorityLevel.INSTITUTIONAL: 2,
            AuthorityLevel.APPROVED_REFERENCE: 3,
            AuthorityLevel.EXTERNAL: 4,
            AuthorityLevel.USER_PROVIDED: 5,
            AuthorityLevel.AI_DERIVED: 6,
        }
        return ranks[self]


class SourceStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class VisibilityScope(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"
    FACULTY = "faculty"
    DEPARTMENT = "department"
    PROGRAMME = "programme"
    COURSE_ONLY = "course_only"


class AssetStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    DRAFT = "draft"


class IngestionStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    READY = "ready"
    FAILED = "failed"


class AssetMimeType(StrEnum):
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    TXT = "text/plain"
    MARKDOWN = "text/markdown"
    HTML = "text/html"
    EPUB = "application/epub+zip"

