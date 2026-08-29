import pytest
from app.domain.tenant.errors import LevelAlreadyArchivedError
from app.domain.tenant.level import Level
from app.domain.tenant.value_objects import (
    LevelCode,
    LevelName,
    LevelStatus,
    TenantId,
)


def test_level_must_belong_to_tenant() -> None:
    level = Level.create(
        tenant_id=TenantId(""),
        code=LevelCode(100),
    )

    assert level.code.value == 100
    assert level.name.value == "100 Level"
    assert level.is_active is True


def test_level_code_validates_futa_rule() -> None:
    with pytest.raises(ValueError):
        LevelCode(150)

    with pytest.raises(ValueError):
        LevelCode(50)

    # FUTA valid
    assert LevelCode(500).value == 500
    assert LevelCode(600).value == 600


def test_level_create_emits_event() -> None:
    level = Level.create(
        tenant_id=TenantId(""),
        code=LevelCode(200),
    )

    events = level.pull_events()
    assert events[0].event_type == "level.created"
    assert events[0].payload["code"] == 200


def test_level_rename_and_archive() -> None:
    level = Level.create(
        tenant_id=TenantId(""),
        code=LevelCode(100),
    )
    level.pull_events()

    level.rename(LevelName("Year 1"))
    assert level.name.value == "Year 1"

    level.archive()
    assert level.status == LevelStatus.ARCHIVED

    with pytest.raises(LevelAlreadyArchivedError):
        level.archive()
