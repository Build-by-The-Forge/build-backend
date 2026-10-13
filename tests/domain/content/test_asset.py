from uuid import UUID

import pytest

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus


def test_create_content_asset_success() -> None:
    sample_sha = "a" * 64
    asset = ContentAsset.create(
        source_id="csrc-1234",
        file_name="CSC301_Lecture_01.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024 * 500,
        content_sha256=sample_sha,
        storage_uri="s3://build-content/futa/csc301/lecture1.pdf",
        tenant_id="tenant-futa",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
        metadata={"pages": 24},
    )

    assert str(UUID(asset.id)) == asset.id and UUID(asset.id).version == 4  # fits VARCHAR(36)
    assert asset.source_id == "csrc-1234"
    assert asset.tenant_id == "tenant-futa"
    assert asset.file_name == "CSC301_Lecture_01.pdf"
    assert asset.mime_type == "application/pdf"
    assert asset.file_size_bytes == 512000
    assert asset.content_sha256 == sample_sha
    assert asset.storage_uri == "s3://build-content/futa/csc301/lecture1.pdf"
    assert asset.asset_version == 1
    assert asset.parent_asset_id is None
    assert asset.status == AssetStatus.ACTIVE
    assert asset.ingestion_status == IngestionStatus.UPLOADED
    assert asset.metadata["pages"] == 24

    events = asset.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.asset_registered"
    assert events[0].payload["content_sha256"] == sample_sha


def test_create_content_asset_invalid_data() -> None:
    valid_sha = "b" * 64

    # Empty source_id
    with pytest.raises(ValueError, match="source_id cannot be empty"):
        ContentAsset.create(
            source_id="   ",
            file_name="doc.pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            content_sha256=valid_sha,
            storage_uri="s3://path",
            created_by="user",
            created_by_email="user@test.com",
        )

    # Empty file_name
    with pytest.raises(ValueError, match="file_name cannot be empty"):
        ContentAsset.create(
            source_id="csrc-1",
            file_name="   ",
            mime_type="application/pdf",
            file_size_bytes=100,
            content_sha256=valid_sha,
            storage_uri="s3://path",
            created_by="user",
            created_by_email="user@test.com",
        )

    # Invalid file size
    with pytest.raises(ValueError, match="file_size_bytes must be greater than 0"):
        ContentAsset.create(
            source_id="csrc-1",
            file_name="doc.pdf",
            mime_type="application/pdf",
            file_size_bytes=0,
            content_sha256=valid_sha,
            storage_uri="s3://path",
            created_by="user",
            created_by_email="user@test.com",
        )

    # Invalid SHA-256
    with pytest.raises(ValueError, match="content_sha256 must be a valid 64-character hex string"):
        ContentAsset.create(
            source_id="csrc-1",
            file_name="doc.pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            content_sha256="short-hash-123",
            storage_uri="s3://path",
            created_by="user",
            created_by_email="user@test.com",
        )

    # Invalid asset version
    with pytest.raises(ValueError, match="asset_version must be at least 1"):
        ContentAsset.create(
            source_id="csrc-1",
            file_name="doc.pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            content_sha256=valid_sha,
            storage_uri="s3://path",
            created_by="user",
            created_by_email="user@test.com",
            asset_version=0,
        )


def test_create_asset_version_lineage() -> None:
    sha_v1 = "1" * 64
    sha_v2 = "2" * 64

    v1_asset = ContentAsset.create(
        source_id="csrc-1234",
        file_name="CSC301_Lecture_v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=sha_v1,
        storage_uri="s3://build-content/futa/v1.pdf",
        tenant_id="tenant-futa",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
    )
    v1_asset.pull_events()

    # Create v2 edition
    v2_asset = v1_asset.create_version(
        file_name="CSC301_Lecture_v2.pdf",
        mime_type="application/pdf",
        file_size_bytes=1200,
        content_sha256=sha_v2,
        storage_uri="s3://build-content/futa/v2.pdf",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
    )

    # Previous version is now SUPERSEDED
    assert v1_asset.status == AssetStatus.SUPERSEDED
    v1_events = v1_asset.pull_events()
    assert len(v1_events) == 1
    assert v1_events[0].event_type == "content.asset_superseded"
    assert v1_events[0].payload["superseded_by_asset_id"] == v2_asset.id

    # New version is ACTIVE, version 2, and references parent
    assert v2_asset.asset_version == 2
    assert v2_asset.parent_asset_id == v1_asset.id
    assert v2_asset.status == AssetStatus.ACTIVE
    assert v2_asset.source_id == "csrc-1234"
    assert v2_asset.tenant_id == "tenant-futa"
    assert v2_asset.content_sha256 == sha_v2

    # Cannot create version with identical SHA-256
    with pytest.raises(ValueError, match="new version must have different content bytes"):
        v2_asset.create_version(
            file_name="CSC301_v3.pdf",
            mime_type="application/pdf",
            file_size_bytes=1200,
            content_sha256=sha_v2,
            storage_uri="s3://build-content/futa/v3.pdf",
            created_by="usr-lecturer",
            created_by_email="lecturer@futa.edu.ng",
        )


def test_asset_revocation_and_ingestion_status() -> None:
    sha = "3" * 64
    asset = ContentAsset.create(
        source_id="csrc-1234",
        file_name="CSC301.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=sha,
        storage_uri="s3://build-content/futa/doc.pdf",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
    )
    asset.pull_events()

    # Progress ingestion status
    asset.update_ingestion_status(IngestionStatus.QUEUED)
    assert asset.ingestion_status == IngestionStatus.QUEUED
    events = asset.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.asset_ingestion_status_updated"
    assert events[0].payload["ingestion_status"] == "queued"

    asset.update_ingestion_status(IngestionStatus.READY)
    assert asset.ingestion_status == IngestionStatus.READY
    ready_events = asset.pull_events()
    assert len(ready_events) == 1
    assert ready_events[0].payload["ingestion_status"] == "ready"

    # Revoke asset
    asset.revoke(reason="Contains outdated copyrighted figures")
    assert asset.status == AssetStatus.REVOKED
    events = asset.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.asset_revoked"

    # Cannot create version from revoked asset
    with pytest.raises(ValueError, match="cannot create a new version of a revoked asset"):
        asset.create_version(
            file_name="CSC301_v2.pdf",
            mime_type="application/pdf",
            file_size_bytes=1000,
            content_sha256="4" * 64,
            storage_uri="s3://build-content/futa/v2.pdf",
            created_by="usr-lecturer",
            created_by_email="lecturer@futa.edu.ng",
        )
