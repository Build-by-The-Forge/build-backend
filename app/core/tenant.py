from dataclasses import dataclass

from fastapi import Request


@dataclass(slots=True)
class TenantContext:
    tenant_id: str | None = None


class TenantResolver:
    def resolve(self, request: Request) -> TenantContext:
        tenant_id = getattr(request, "headers", {}).get("x-tenant-id")
        return TenantContext(tenant_id=tenant_id)
