import re
from dataclasses import dataclass


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
        if len(self.value) < 12:
            raise ValueError("password must be at least 12 characters")


@dataclass(frozen=True, slots=True)
class PasswordHash:
    value: str


@dataclass(frozen=True, slots=True)
class UserId:
    value: str


class PasswordHasher:
    def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(f"hashed:{password.value}")


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
