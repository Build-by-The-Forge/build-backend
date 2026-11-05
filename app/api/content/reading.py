"""The caller of a content route, as the read policy sees them (M3-D ruling B).

A route that lists, returns or streams a document or its job takes a
``Caller`` from ``reading(permission)``: the permission check it always had,
plus the ``Reader`` the one policy needs, built from the verified tenant
context only. tests/integration/content/test_read_policy_routes.py fails
on any ``/content`` route that takes neither this nor a stated exemption.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends

from app.application.content.read_policy import ContentReadService, Reader
from app.bootstrap.container import build_container
from app.core.authorization import Permission, authorization
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext

read_service = build_container().get(ContentReadService)


@dataclass(frozen=True, slots=True)
class Caller:
    context: TenantContext
    reader: Reader


def reading(permission: Permission) -> Callable[..., Caller]:
    def caller(context: TenantContext = Depends(require_permission(permission))) -> Caller:
        return Caller(
            context=context,
            reader=Reader(
                tenant_id=context.tenant_id or "",
                user_id=context.user_id,
                # Managing shared material, never access to students' private documents.
                manages_shared=authorization.can(context, Permission.CONTENT_SOURCE_MANAGE),
            ),
        )

    caller.__read_policy__ = True  # type: ignore[attr-defined]
    return caller
