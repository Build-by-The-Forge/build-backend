import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

PASSWORD_MIN_LENGTH = 12
# Bounds hashing cost per request (Argon2 work grows with input length).
PASSWORD_MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("invalid email format")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class Password:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
        if len(self.value) > PASSWORD_MAX_LENGTH:
            raise ValueError(f"password must be at most {PASSWORD_MAX_LENGTH} characters")


@dataclass(frozen=True, slots=True)
class PasswordHash:
    value: str


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


# Unverified accounts may sign in; their tenant capabilities are restricted
# elsewhere. Every other non-active status is refused outright.
AUTHENTICATABLE_STATUSES = frozenset(
    {AccountStatus.ACTIVE, AccountStatus.PENDING_VERIFICATION}
)


@dataclass(frozen=True, slots=True)
class UserId:
    value: str


class PasswordHasher(Protocol):
    def hash(self, password: Password) -> PasswordHash: ...


@dataclass(frozen=True, slots=True)
class RoleId:
    value: str


@dataclass(frozen=True, slots=True)
class PermissionId:
    value: str


@dataclass(frozen=True, slots=True)
class Permission:
    id: PermissionId
    resource: str
    action: str


@dataclass(frozen=True, slots=True)
class Role:
    id: RoleId
    name: str
    permissions: tuple[Permission, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionId:
    value: str


@dataclass(frozen=True, slots=True)
class DeviceId:
    value: str


@dataclass(frozen=True, slots=True)
class RefreshTokenHash:
    value: str


@dataclass(frozen=True, slots=True)
class RefreshTokenId:
    value: str
