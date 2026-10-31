"""What a reader who doesn't manage content may see of it.

Storage locations, identities and processing internals are for staff. This
is enforced here, on every read route, not left to the client (gap G-06).
"""

from typing import Any

from app.core.authorization import Permission, authorization
from app.core.tenant_context import TenantContext

_ASSET_INTERNALS = frozenset({"storage_uri", "created_by", "created_by_email", "tenant_id", "metadata"})
_SOURCE_INTERNALS = frozenset({"trust_policy", "created_by", "created_by_email", "tenant_id"})
_JOB_INTERNALS = frozenset(
    {
        "tenant_id",
        "created_by",
        "correlation_id",
        "external_task_id",
        "attempt_history",
        "error_details",
        "metrics",
        "last_dispatched_at",
        "last_callback_at",
    }
)


def _view(payload: dict[str, Any], context: TenantContext, manage: Permission, internals: frozenset[str]) -> dict[str, Any]:
    if authorization.can(context, manage):
        return payload
    return {key: value for key, value in payload.items() if key not in internals}


def asset_view(payload: dict[str, Any], context: TenantContext) -> dict[str, Any]:
    return _view(payload, context, Permission.CONTENT_ASSET_UPLOAD, _ASSET_INTERNALS)


def source_view(payload: dict[str, Any], context: TenantContext) -> dict[str, Any]:
    return _view(payload, context, Permission.CONTENT_SOURCE_MANAGE, _SOURCE_INTERNALS)


def job_view(payload: dict[str, Any], context: TenantContext) -> dict[str, Any]:
    return _view(payload, context, Permission.CONTENT_JOB_MANAGE, _JOB_INTERNALS)
