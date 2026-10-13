"""The signed service context (docs/phase1-m3-boundary-design.md, A.4).

The context says on whose behalf, within which tenant, a service call is
made. It is validated strictly in both directions: a context that does not
match the schema exactly is refused, whoever signed it.

Backend → AI-service, ``permissions`` records an authorization decision the
backend already made. AI-service → backend, the context only identifies the
tenant a task reports about; it grants nothing (B.3).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

CONTEXT_VERSION = 1
ACTOR_USER = "user"
ACTOR_SYSTEM = "system"

CONTEXT_FIELDS = frozenset(
    {
        "v",
        "actor",
        "tenant_id",
        "user_id",
        "membership_id",
        "role",
        "permissions",
        "correlation_id",
    }
)

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_CORRELATION_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class InvalidServiceContext(ValueError):
    """The context does not satisfy A.4. The message is for internal logs."""


def _is_str(value: Any) -> bool:
    return type(value) is str


def _require_uuid(name: str, value: Any) -> None:
    if not _is_str(value) or not _UUID_RE.fullmatch(value):
        raise InvalidServiceContext(f"{name} is not a canonical lowercase UUID")


def _require_null(name: str, value: Any) -> None:
    if value is not None:
        raise InvalidServiceContext(f"{name} must be null for a system actor")


@dataclass(frozen=True)
class ServiceContext:
    actor: str
    tenant_id: str
    correlation_id: str
    user_id: str | None = None
    membership_id: str | None = None
    role: str | None = None
    permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_uuid("tenant_id", self.tenant_id)
        if not _is_str(self.correlation_id) or not _CORRELATION_ID_RE.fullmatch(self.correlation_id):
            raise InvalidServiceContext("correlation_id is malformed")
        if type(self.permissions) is not tuple or not all(_is_str(p) and p for p in self.permissions):
            raise InvalidServiceContext("permissions must be non-empty strings")
        if list(self.permissions) != sorted(set(self.permissions)):
            raise InvalidServiceContext("permissions must be sorted and unique")

        if self.actor == ACTOR_USER:
            _require_uuid("user_id", self.user_id)
            _require_uuid("membership_id", self.membership_id)
            if not _is_str(self.role) or not self.role:
                raise InvalidServiceContext("role must be a non-empty string")
        elif self.actor == ACTOR_SYSTEM:
            _require_null("user_id", self.user_id)
            _require_null("membership_id", self.membership_id)
            _require_null("role", self.role)
            if self.permissions:
                raise InvalidServiceContext("permissions must be empty for a system actor")
        else:
            raise InvalidServiceContext("actor must be 'user' or 'system'")

    @classmethod
    def for_user(
        cls,
        *,
        tenant_id: str,
        user_id: str,
        membership_id: str,
        role: str,
        permissions: Iterable[str],
        correlation_id: str,
    ) -> "ServiceContext":
        """A user context carries only the permissions checked for this
        operation (normally one), never the user's full set (E.6)."""
        return cls(
            actor=ACTOR_USER,
            tenant_id=tenant_id,
            user_id=user_id,
            membership_id=membership_id,
            role=role,
            permissions=tuple(sorted(set(permissions))),
            correlation_id=correlation_id,
        )

    @classmethod
    def for_system(cls, *, tenant_id: str, correlation_id: str) -> "ServiceContext":
        return cls(actor=ACTOR_SYSTEM, tenant_id=tenant_id, correlation_id=correlation_id)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceContext":
        """Parse a decoded context. Every field must be present, no other
        field may appear, and every value must have exactly the A.4 type."""
        keys = set(data)
        if keys != CONTEXT_FIELDS:
            missing = sorted(CONTEXT_FIELDS - keys)
            unknown = sorted(keys - CONTEXT_FIELDS)
            raise InvalidServiceContext(f"fields: missing {missing}, unknown {unknown}")
        version = data["v"]
        if type(version) is not int or version != CONTEXT_VERSION:
            raise InvalidServiceContext("v must be the integer 1")
        if not _is_str(data["actor"]):
            raise InvalidServiceContext("actor must be a string")
        permissions = data["permissions"]
        if type(permissions) is not list:
            raise InvalidServiceContext("permissions must be an array")
        return cls(
            actor=data["actor"],
            tenant_id=data["tenant_id"],
            correlation_id=data["correlation_id"],
            user_id=data["user_id"],
            membership_id=data["membership_id"],
            role=data["role"],
            permissions=tuple(permissions),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": CONTEXT_VERSION,
            "actor": self.actor,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "membership_id": self.membership_id,
            "role": self.role,
            "permissions": list(self.permissions),
            "correlation_id": self.correlation_id,
        }
