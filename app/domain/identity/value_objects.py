import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.domain.client_safe import ClientSafeError

PASSWORD_MIN_LENGTH = 12
# Bounds hashing cost per request (Argon2 work grows with input length).
PASSWORD_MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ClientSafeError("invalid email format")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class Password:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) < PASSWORD_MIN_LENGTH:
            raise ClientSafeError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
        if len(self.value) > PASSWORD_MAX_LENGTH:
            raise ClientSafeError(f"password must be at most {PASSWORD_MAX_LENGTH} characters")


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
AUTHENTICATABLE_STATUSES = frozenset({AccountStatus.ACTIVE, AccountStatus.PENDING_VERIFICATION})


@dataclass(frozen=True, slots=True)
class UserId:
    value: str


class PasswordHasher(Protocol):
    def hash(self, password: Password) -> PasswordHash: ...


@dataclass(frozen=True, slots=True)
class SessionId:
    value: str


@dataclass(frozen=True, slots=True)
class DeviceId:
    value: str


@dataclass(frozen=True, slots=True)
class RefreshTokenHash:
    value: str
