from datetime import date

import pytest
from app.domain.tenant.academic_session import AcademicSession
from app.domain.tenant.errors import AcademicSessionAlreadyArchivedError
from app.domain.tenant.value_objects import (
    AcademicSessionName,
    AcademicSessionSlug,
    AcademicSessionStatus,
    TenantId,
)


def test_academic_session_name_validates() -> None:
    with pytest.raises(ValueError):
        AcademicSessionName("2025-2026")

    with pytest.raises(ValueError):
        AcademicSessionName("2025/2027")

    name = AcademicSessionName("2025/2026")
    assert name.value == "2025/2026"


def test_academic_session_create() -> None:
    session = AcademicSession.create(
        tenant_id=TenantId(""),
        name=AcademicSessionName("2025/2026"),
        slug=AcademicSessionSlug("2025-2026"),
        start_date=date(2025, 9, 1),
        end_date=date(2026, 7, 31),
        is_current=True,
    )

    assert session.is_current is True
    assert session.is_active is True
    assert session.slug.value == "2025-2026"


def test_academic_session_dates_validate() -> None:
    with pytest.raises(ValueError):
        AcademicSession.create(
            tenant_id=TenantId(""),
            name=AcademicSessionName("2025/2026"),
            slug=AcademicSessionSlug("2025-2026"),
            start_date=date(2026, 7, 31),
            end_date=date(2025, 9, 1),
        )


def test_academic_session_mark_current_and_archive() -> None:
    session = AcademicSession.create(
        tenant_id=TenantId(""),
        name=AcademicSessionName("2024/2025"),
        slug=AcademicSessionSlug("2024-2025"),
        start_date=date(2024, 9, 1),
        end_date=date(2025, 7, 31),
    )
    session.pull_events()

    session.mark_as_current()
    assert session.is_current is True

    session.archive()
    assert session.status == AcademicSessionStatus.ARCHIVED
    assert session.is_current is False

    with pytest.raises(AcademicSessionAlreadyArchivedError):
        session.archive()
