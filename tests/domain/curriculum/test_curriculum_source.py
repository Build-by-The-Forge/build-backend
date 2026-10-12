from uuid import UUID

import pytest
from app.domain.curriculum.source import (
    CurriculumSource,
    SnapshotStatus,
    SourceStatus,
)


def test_create_curriculum_source_success() -> None:
    source = CurriculumSource.create(
        code="nuc_ccmas",
        name="National Universities Commission CCMAS",
        base_url="https://ccmas.nuc.edu.ng",
        source_type="official_benchmark",
        sync_frequency_days=30,
        parser_version="v1.0",
    )

    assert str(UUID(source.id)) == source.id  # fits VARCHAR(36)
    assert source.code == "NUC_CCMAS"
    assert source.name == "National Universities Commission CCMAS"
    assert source.base_url == "https://ccmas.nuc.edu.ng"
    assert source.status == SourceStatus.ACTIVE
    assert source.sync_frequency_days == 30
    assert source.parser_version == "v1.0"

    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "curriculum.source_created"
    assert events[0].payload["code"] == "NUC_CCMAS"


def test_create_curriculum_source_invalid_data() -> None:
    with pytest.raises(ValueError, match="source code cannot be empty"):
        CurriculumSource.create(
            code="   ",
            name="Valid Name",
            base_url="https://example.com",
        )

    with pytest.raises(ValueError, match="source name cannot be empty"):
        CurriculumSource.create(
            code="CODE1",
            name="   ",
            base_url="https://example.com",
        )

    with pytest.raises(ValueError, match="source base_url cannot be empty"):
        CurriculumSource.create(
            code="CODE1",
            name="Valid Name",
            base_url="   ",
        )

    with pytest.raises(ValueError, match="sync_frequency_days must be at least 1"):
        CurriculumSource.create(
            code="CODE1",
            name="Valid Name",
            base_url="https://example.com",
            sync_frequency_days=0,
        )


def test_curriculum_source_status_transitions() -> None:
    source = CurriculumSource.create(
        code="NUC_CCMAS",
        name="CCMAS",
        base_url="https://example.com",
    )
    source.pull_events()

    source.disable()
    assert source.status == SourceStatus.DISABLED
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "curriculum.source_disabled"

    source.enable()
    assert source.status == SourceStatus.ACTIVE
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "curriculum.source_enabled"


def test_create_snapshot_success() -> None:
    source = CurriculumSource.create(
        code="NUC_CCMAS",
        name="CCMAS",
        base_url="https://example.com",
        parser_version="v1.2",
    )
    source.pull_events()

    sample_sha = "a" * 64
    snapshot = source.create_snapshot(
        source_url="https://example.com/computer-science.pdf",
        content_sha256=sample_sha,
        raw_artifact_uri="s3://build-artifacts/ccmas/csc.pdf",
    )

    assert str(UUID(snapshot.id)) == snapshot.id  # fits VARCHAR(36)
    assert snapshot.source_id == source.id
    assert snapshot.source_url == "https://example.com/computer-science.pdf"
    assert snapshot.content_sha256 == sample_sha
    assert snapshot.raw_artifact_uri == "s3://build-artifacts/ccmas/csc.pdf"
    assert snapshot.parser_version == "v1.2"
    assert snapshot.status == SnapshotStatus.CAPTURED

    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "curriculum.snapshot_captured"
    assert events[0].payload["snapshot_id"] == snapshot.id
    assert events[0].payload["content_sha256"] == sample_sha


def test_create_snapshot_on_disabled_source_raises() -> None:
    source = CurriculumSource.create(
        code="NUC_CCMAS",
        name="CCMAS",
        base_url="https://example.com",
    )
    source.disable()

    with pytest.raises(ValueError, match="cannot create snapshot for a disabled curriculum source"):
        source.create_snapshot(
            source_url="https://example.com/csc.pdf",
            content_sha256="a" * 64,
            raw_artifact_uri="s3://uri",
        )


def test_create_snapshot_invalid_hash() -> None:
    source = CurriculumSource.create(
        code="NUC_CCMAS",
        name="CCMAS",
        base_url="https://example.com",
    )

    with pytest.raises(ValueError, match="content_sha256 must be a valid 64-character hex string"):
        source.create_snapshot(
            source_url="https://example.com/csc.pdf",
            content_sha256="short-hash",
            raw_artifact_uri="s3://uri",
        )
