from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: str
    tenant_id: str
    membership_id: str
    role: str
