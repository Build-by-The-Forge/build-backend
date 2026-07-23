from dataclasses import dataclass


@dataclass(slots=True)
class TenantContext:
    tenant_id: str | None = None


class TenantResolver:
    def resolve(self, request) -> TenantContext:
        tenant_id = getattr(request, "headers", {}).get("x-tenant-id")
        return TenantContext(tenant_id=tenant_id)
