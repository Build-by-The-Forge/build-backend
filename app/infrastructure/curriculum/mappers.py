from __future__ import annotations

from app.domain.curriculum.source import (
    CurriculumSnapshot,
    CurriculumSource,
    SnapshotStatus,
    SourceStatus,
)
from app.infrastructure.db.models.curriculum import (
    CurriculumSnapshotModel,
    CurriculumSourceModel,
)


def curriculum_source_to_model(
    source: CurriculumSource, model: CurriculumSourceModel | None = None
) -> CurriculumSourceModel:
    if model is None:
        return CurriculumSourceModel(
            id=source.id,
            code=source.code,
            name=source.name,
            base_url=source.base_url,
            source_type=source.source_type,
            status=source.status.value,
            sync_frequency_days=source.sync_frequency_days,
            parser_version=source.parser_version,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
    model.code = source.code
    model.name = source.name
    model.base_url = source.base_url
    model.source_type = source.source_type
    model.status = source.status.value
    model.sync_frequency_days = source.sync_frequency_days
    model.parser_version = source.parser_version
    model.updated_at = source.updated_at
    return model


def curriculum_source_model_to_domain(
    model: CurriculumSourceModel,
) -> CurriculumSource:
    return CurriculumSource(
        id=model.id,
        code=model.code,
        name=model.name,
        base_url=model.base_url,
        source_type=model.source_type,
        status=SourceStatus(model.status),
        sync_frequency_days=model.sync_frequency_days,
        parser_version=model.parser_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def curriculum_snapshot_to_model(
    snapshot: CurriculumSnapshot,
) -> CurriculumSnapshotModel:
    return CurriculumSnapshotModel(
        id=snapshot.id,
        source_id=snapshot.source_id,
        source_url=snapshot.source_url,
        retrieved_at=snapshot.retrieved_at,
        content_sha256=snapshot.content_sha256,
        raw_artifact_uri=snapshot.raw_artifact_uri,
        parser_version=snapshot.parser_version,
        status=snapshot.status.value,
        created_at=snapshot.created_at,
    )


def curriculum_snapshot_model_to_domain(
    model: CurriculumSnapshotModel,
) -> CurriculumSnapshot:
    return CurriculumSnapshot(
        id=model.id,
        source_id=model.source_id,
        source_url=model.source_url,
        retrieved_at=model.retrieved_at,
        content_sha256=model.content_sha256,
        raw_artifact_uri=model.raw_artifact_uri,
        parser_version=model.parser_version,
        status=SnapshotStatus(model.status),
        created_at=model.created_at,
    )
