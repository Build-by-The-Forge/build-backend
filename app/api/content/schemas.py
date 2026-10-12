from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContentSourceCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, description="Unique source code")
    name: str = Field(..., min_length=2, max_length=255, description="Source display name")
    source_type: str = Field(
        ...,
        description="ccmas | textbook | lecturer_upload | admin_upload | course_material | web_source",
    )
    authority_level: str = Field(
        ...,
        description="regulatory | institutional | approved_reference | external | user_provided | ai_derived",
    )
    visibility: str = Field(
        ...,
        description="platform | tenant | faculty | department | programme | course_only",
    )
    faculty_id: str | None = Field(default=None, description="Faculty ID if faculty visibility")
    department_id: str | None = Field(default=None, description="Department ID if department visibility")
    programme_id: str | None = Field(default=None, description="Programme ID if programme visibility")
    description: str | None = Field(default=None, description="Optional description")
    author_name: str | None = Field(default=None, description="Author or instructor name")
    publisher: str | None = Field(default=None, description="Publisher name")
    isbn_or_doi: str | None = Field(default=None, description="ISBN or DOI")
    source_url: str | None = Field(default=None, description="Origin URL or repository link")
    trust_policy: dict[str, Any] = Field(default_factory=dict, description="Custom trust and indexing rules")


class ContentSourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    author_name: str | None = None
    publisher: str | None = None
    isbn_or_doi: str | None = None
    source_url: str | None = None
    trust_policy: dict[str, Any] | None = None


class ContentSourceReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Reason for status transition")


class ContentSourceResponse(BaseModel):
    id: str
    code: str
    name: str
    source_type: str
    authority_level: str
    visibility: str
    status: str
    tenant_id: str | None
    faculty_id: str | None
    department_id: str | None
    programme_id: str | None
    description: str | None
    author_name: str | None
    publisher: str | None
    isbn_or_doi: str | None
    source_url: str | None
    trust_policy: dict[str, Any]
    created_by: str
    created_by_email: str
    created_at: str
    updated_at: str
