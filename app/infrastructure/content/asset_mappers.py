from __future__ import annotations

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus
from app.infrastructure.db.models.content import ContentAssetModel


def content_asset_to_model(
    asset: ContentAsset, model: ContentAssetModel | None = None
) -> ContentAssetModel:
    if model is None:
        model = ContentAssetModel(id=asset.id)

    model.source_id = asset.source_id
    model.tenant_id = asset.tenant_id
    model.file_name = asset.file_name
    model.mime_type = asset.mime_type
    model.file_size_bytes = asset.file_size_bytes
    model.content_sha256 = asset.content_sha256
    model.storage_uri = asset.storage_uri
    model.asset_version = asset.asset_version
    model.parent_asset_id = asset.parent_asset_id
    model.status = asset.status.value
    model.ingestion_status = asset.ingestion_status.value
    model.metadata_json = dict(asset.metadata)
    model.created_by = asset.created_by
    model.created_by_email = asset.created_by_email
    model.created_at = asset.created_at
    model.updated_at = asset.updated_at
    return model


def content_asset_model_to_domain(model: ContentAssetModel) -> ContentAsset:
    return ContentAsset(
        id=model.id,
        source_id=model.source_id,
        tenant_id=model.tenant_id,
        file_name=model.file_name,
        mime_type=model.mime_type,
        file_size_bytes=model.file_size_bytes,
        content_sha256=model.content_sha256,
        storage_uri=model.storage_uri,
        asset_version=model.asset_version,
        parent_asset_id=model.parent_asset_id,
        status=AssetStatus(model.status),
        ingestion_status=IngestionStatus(model.ingestion_status),
        metadata=dict(model.metadata_json) if model.metadata_json else {},
        created_by=model.created_by,
        created_by_email=model.created_by_email,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
