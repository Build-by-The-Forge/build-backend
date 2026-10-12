from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.curriculum.source import (
    CurriculumSnapshot,
    CurriculumSource,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)


@pytest.mark.asyncio
async def test_curriculum_source_persistence_round_trip(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_CCMAS_PERSIST",
        name="CCMAS Persist",
        base_url="https://ccmas.example.com",
        source_type="official_benchmark",
        sync_frequency_days=15,
        parser_version="v2.0",
    )
    await repository.save_source(source)

    retrieved = await repository.get_source_by_id(source.id)
    assert retrieved is not None
    assert retrieved.id == source.id
    assert retrieved.code == "NUC_CCMAS_PERSIST"
    assert retrieved.name == "CCMAS Persist"
    assert retrieved.sync_frequency_days == 15
    assert retrieved.parser_version == "v2.0"

    retrieved_by_code = await repository.get_source_by_code("nuc_ccmas_persist")
    assert retrieved_by_code is not None
    assert retrieved_by_code.id == source.id

    sources = await repository.list_sources()
    assert any(s.code == "NUC_CCMAS_PERSIST" for s in sources)


@pytest.mark.asyncio
async def test_curriculum_snapshot_persistence_and_queries(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_SNAPSHOT_TEST",
        name="Snapshot Test",
        base_url="https://snapshot.example.com",
    )
    await repository.save_source(source)

    sha1 = "1" * 64
    sha2 = "2" * 64

    snap1 = source.create_snapshot(
        source_url="https://snapshot.example.com/v1.pdf",
        content_sha256=sha1,
        raw_artifact_uri="s3://build-artifacts/ccmas/v1.pdf",
        retrieved_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    await repository.save_snapshot(snap1)

    snap2 = source.create_snapshot(
        source_url="https://snapshot.example.com/v2.pdf",
        content_sha256=sha2,
        raw_artifact_uri="s3://build-artifacts/ccmas/v2.pdf",
        retrieved_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
    )
    await repository.save_snapshot(snap2)

    # Test latest snapshot lookup
    latest = await repository.get_latest_snapshot(source.id)
    assert latest is not None
    assert latest.id == snap2.id
    assert latest.content_sha256 == sha2

    # Test hash lookup
    retrieved_by_hash = await repository.get_snapshot_by_hash(source.id, sha1)
    assert retrieved_by_hash is not None
    assert retrieved_by_hash.id == snap1.id

    # Test listing and pagination
    snapshots, total = await repository.list_snapshots(source.id, limit=10, offset=0)
    assert total == 2
    assert len(snapshots) == 2
    assert snapshots[0].id == snap2.id  # Latest first
    assert snapshots[1].id == snap1.id


@pytest.mark.asyncio
async def test_duplicate_snapshot_hash_constraint_enforced(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_UNIQUE_HASH_TEST",
        name="Unique Hash Test",
        base_url="https://unique.example.com",
    )
    await repository.save_source(source)

    duplicate_sha = "f" * 64
    snap1 = source.create_snapshot(
        source_url="https://unique.example.com/file.pdf",
        content_sha256=duplicate_sha,
        raw_artifact_uri="s3://path/1",
    )
    await repository.save_snapshot(snap1)

    snap2 = CurriculumSnapshot.create(
        source_id=source.id,
        source_url="https://unique.example.com/file.pdf",
        content_sha256=duplicate_sha,
        raw_artifact_uri="s3://path/2",
        parser_version="v1.0",
    )
    with pytest.raises(IntegrityError):
        await repository.save_snapshot(snap2)
