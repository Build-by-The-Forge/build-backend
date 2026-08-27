from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    Password,
    PasswordHash,
    PasswordHasher,
    RefreshTokenHash,
    RefreshTokenId,
    Role,
    SessionId,
    UserId,
)
from app.events.base import DomainEvent


@dataclass(slots=True)
class User:
    id: UserId
    email: Email
    password_hash: PasswordHash
    is_active: bool = True
    created_at: datetime | None = None
    roles: list[Role] = field(default_factory=list)
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.id.value == "":
            self.id = UserId(str(uuid4()))
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def change_password(self, new_password: Password, hasher: PasswordHasher) -> None:
        self.password_hash = hasher.hash(new_password)

    def assign_role(self, role: Role) -> None:
        if role not in self.roles:
            self.roles.append(role)

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


@dataclass(slots=True)
class Session:
    id: SessionId
    user_id: UserId
    device_id: DeviceId | None = None
    refresh_token_hash: RefreshTokenHash | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.last_seen_at is None:
            self.last_seen_at = self.created_at

    def revoke(self) -> None:
        self.revoked_at = datetime.now(timezone.utc)

    def touch(self) -> None:
        self.last_seen_at = datetime.now(timezone.utc)

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


@dataclass(slots=True)
class Device:
    id: DeviceId
    platform: str
    manufacturer: str | None = None
    model: str | None = None
    trusted: bool = False
    fingerprint: str | None = None
    last_seen: datetime | None = None

    def __post_init__(self) -> None:
        if self.last_seen is None:
            self.last_seen = datetime.now(timezone.utc)

    def mark_trusted(self) -> None:
        self.trusted = True

    def touch(self) -> None:
        self.last_seen = datetime.now(timezone.utc)


@dataclass(slots=True)
class RefreshToken:
    id: RefreshTokenId
    session_id: SessionId
    token_hash: RefreshTokenHash
    expires_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.expires_at is None:
            self.expires_at = datetime.now(timezone.utc)
        if self.rotated_at is None:
            self.rotated_at = datetime.now(timezone.utc)

    def revoke(self) -> None:
        self.revoked_at = datetime.now(timezone.utc)

    def rotate(self, new_hash: RefreshTokenHash) -> None:
        self.token_hash = new_hash
        self.rotated_at = datetime.now(timezone.utc)
