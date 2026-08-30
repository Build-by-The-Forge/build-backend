from __future__ import annotations

from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.infrastructure.db.models.content import ContentSourceModel


def content_source_to_model(
    source: ContentSource, model: ContentSourceModel | None = None
) -> ContentSourceModel:
    if model is None:
        model = ContentSourceModel(id=source.id)

    model.code = source.code
    model.name = source.name
    model.source_type = source.source_type.value
    model.authority_level = source.authority_level.value
    model.visibility = source.visibility.value
    model.status = source.status.value
    model.tenant_id = source.tenant_id
    model.faculty_id = source.faculty_id
    model.department_id = source.department_id
    model.programme_id = source.programme_id
    model.description = source.description
    model.author_name = source.author_name
    model.publisher = source.publisher
    model.isbn_or_doi = source.isbn_or_doi
    model.source_url = source.source_url
    model.trust_policy = source.trust_policy
    model.created_by = source.created_by
    model.created_by_email = source.created_by_email
    model.created_at = source.created_at
    model.updated_at = source.updated_at
    return model


def content_source_model_to_domain(model: ContentSourceModel) -> ContentSource:
    return ContentSource(
        id=model.id,
        code=model.code,
        name=model.name,
        source_type=ContentSourceType(model.source_type),
        authority_level=AuthorityLevel(model.authority_level),
        visibility=VisibilityScope(model.visibility),
        status=SourceStatus(model.status),
        created_by=model.created_by,
        created_by_email=model.created_by_email,
        tenant_id=model.tenant_id,
        faculty_id=model.faculty_id,
        department_id=model.department_id,
        programme_id=model.programme_id,
        description=model.description,
        author_name=model.author_name,
        publisher=model.publisher,
        isbn_or_doi=model.isbn_or_doi,
        source_url=model.source_url,
        trust_policy=dict(model.trust_policy) if model.trust_policy else {},
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
