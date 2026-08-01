import pytest
from app.domain.tenant.errors import TenantAlreadyArchivedError
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    TenantId,
    TenantName,
    TenantSlug,
    TenantStatus,
)


def test_tenant_id_generates_when_empty() -> None:
    tid = TenantId("")
    assert len(tid.value) > 0


def test_tenant_slug_normalizes_and_validates() -> None:
    slug = TenantSlug("FUTA ")
    assert slug.value == "futa"

    with pytest.raises(ValueError):
        TenantSlug("ab")

    with pytest.raises(ValueError):
        TenantSlug("Invalid Slug!")


def test_tenant_name_validates() -> None:
    with pytest.raises(ValueError):
        TenantName("A")

    name = TenantName(" Federal University of Technology Akure ")
    assert name.value == "Federal University of Technology Akure"


def test_tenant_create_emits_event() -> None:
    tenant = Tenant.create(name=TenantName("FUTA"), slug=TenantSlug("futa"))

    assert tenant.is_active is True
    assert tenant.status == TenantStatus.ACTIVE
    events = tenant.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "tenant.created"
    assert tenant.pull_events() == []


def test_tenant_rename_and_archive() -> None:
    tenant = Tenant.create(name=TenantName("FUTA"), slug=TenantSlug("futa"))
    tenant.pull_events()

    tenant.rename(TenantName("FUTA - Akure"))
    assert tenant.name.value == "FUTA - Akure"
    assert tenant.pull_events()[0].event_type == "tenant.updated"

    tenant.archive()
    assert tenant.status == TenantStatus.ARCHIVED

    with pytest.raises(TenantAlreadyArchivedError):
        tenant.archive()
