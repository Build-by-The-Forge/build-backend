"""Who may write content (P3-1 PR 3a).

One rule for every route that creates or changes a content source or
asset, applied to the caller's verified tenant (``TenantContext``), never
to a tenant named by the client:

- content of another tenant does not exist for the caller (404, and the
  message names neither the owner nor the reason);
- platform content (``tenant_id`` None) cannot be written from a tenant
  context (403): no platform-administrator path exists yet, and a tenant
  member must not change what every tenant sees.

A ``None`` caller tenant is a system-level call (no tenant context), which
no HTTP route makes; it is left to the caller's own rules.

Reading is a different rule: platform content stays readable by every
tenant (``ContentSource.is_accessible_by``).
"""

from __future__ import annotations


class ContentAccessError(ValueError):
    """A refused content write. A ValueError, so existing handlers still
    catch it; routes map it by class, not by message."""

    status_code = 400
    code = "CONTENT_ACCESS_DENIED"


class ContentNotFoundError(ContentAccessError):
    status_code = 404
    code = "CONTENT_NOT_FOUND"


class PlatformContentNotWritableError(ContentAccessError):
    status_code = 403
    code = "PLATFORM_CONTENT_NOT_WRITABLE"


def ensure_tenant_may_write(owner_tenant_id: str | None, caller_tenant_id: str | None, *, what: str) -> None:
    """Refuse a write by ``caller_tenant_id`` to content owned by
    ``owner_tenant_id`` (None: platform content)."""
    if caller_tenant_id is None:
        return
    if owner_tenant_id is None:
        raise PlatformContentNotWritableError(f"platform {what}s cannot be changed from a tenant")
    if owner_tenant_id != caller_tenant_id:
        raise ContentNotFoundError(f"{what} not found")
