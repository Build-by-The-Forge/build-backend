import pytest

from app.application.content.access import (
    ContentNotFoundError,
    PlatformContentNotWritableError,
    ensure_tenant_may_write,
)


def test_a_tenant_may_write_its_own_content() -> None:
    ensure_tenant_may_write("tenant-a", "tenant-a", what="asset")


def test_another_tenants_content_does_not_exist_and_the_owner_is_not_named() -> None:
    with pytest.raises(ContentNotFoundError) as caught:
        ensure_tenant_may_write("tenant-a", "tenant-b", what="asset")

    assert caught.value.status_code == 404
    assert "tenant-a" not in str(caught.value)


def test_platform_content_is_not_writable_from_a_tenant() -> None:
    with pytest.raises(PlatformContentNotWritableError) as caught:
        ensure_tenant_may_write(None, "tenant-b", what="source")

    assert caught.value.status_code == 403


def test_a_system_call_without_a_tenant_context_is_left_to_its_caller() -> None:
    ensure_tenant_may_write(None, None, what="asset")
    ensure_tenant_may_write("tenant-a", None, what="asset")
