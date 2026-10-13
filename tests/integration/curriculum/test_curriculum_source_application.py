import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.curriculum.curriculum_source_service import (
    CurriculumSourceService,
)
from app.events.event_bus import EventBus
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)


@pytest.mark.asyncio
async def test_curriculum_source_service_registration_and_drift(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyCurriculumSourceRepository(session)
    event_bus = EventBus()
    captured_events: list[str] = []

    def listener(event: object) -> None:
        if hasattr(event, "event_type"):
            captured_events.append(event.event_type)

    event_bus.subscribe("curriculum.source_created", listener)
    event_bus.subscribe("curriculum.snapshot_captured", listener)

    service = CurriculumSourceService(
        repository=repository,
        event_bus=event_bus,
    )

    # 1. Register Source
    source = await service.register_source(
        code="NUC_CCMAS_APP_TEST",
        name="CCMAS Application Test",
        base_url="https://ccmas.example.com",
    )
    assert source.code == "NUC_CCMAS_APP_TEST"
    assert "curriculum.source_created" in captured_events

    # 2. Duplicate registration fails
    with pytest.raises(ValueError, match="already exists"):
        await service.register_source(
            code="NUC_CCMAS_APP_TEST",
            name="CCMAS Duplicate",
            base_url="https://ccmas.example.com",
        )

    # 3. First Snapshot Record -> Drift detected (New snapshot captured)
    sha_v1 = "1" * 64
    snap1, drift1 = await service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.example.com/spec.pdf",
        content_sha256=sha_v1,
        raw_artifact_uri="s3://build-artifacts/ccmas/v1.pdf",
    )
    assert drift1 is True
    assert snap1.content_sha256 == sha_v1
    assert "curriculum.snapshot_captured" in captured_events

    captured_events.clear()

    # 4. Record identical hash -> No drift (Idempotent no-op)
    snap1_repeat, drift1_repeat = await service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.example.com/spec.pdf",
        content_sha256=sha_v1,
        raw_artifact_uri="s3://build-artifacts/ccmas/v1.pdf",
    )
    assert drift1_repeat is False
    assert snap1_repeat.id == snap1.id
    assert len(captured_events) == 0  # No new snapshot event emitted

    # 5. Record new hash -> Drift detected (New snapshot captured)
    sha_v2 = "2" * 64
    snap2, drift2 = await service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.example.com/spec.pdf",
        content_sha256=sha_v2,
        raw_artifact_uri="s3://build-artifacts/ccmas/v2.pdf",
    )
    assert drift2 is True
    assert snap2.id != snap1.id
    assert snap2.content_sha256 == sha_v2
    assert "curriculum.snapshot_captured" in captured_events

    # 6. List snapshots
    res = await service.list_snapshots(source_id=source.id, limit=10, offset=0)
    assert res is not None
    snapshots, total = res
    assert total == 2
    assert len(snapshots) == 2
    assert snapshots[0].id == snap2.id
    assert snapshots[1].id == snap1.id
