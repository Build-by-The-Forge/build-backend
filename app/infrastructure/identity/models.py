from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserStatus(PyEnum):
    ACTIVE = "ACTIVE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


role_permissions_table = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        String(36),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        String(36),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=False),
        default=UserStatus.PENDING_VERIFICATION,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    roles: Mapped[list["RoleModel"]] = relationship(
        "RoleModel",
        secondary="role_assignments",
        back_populates="users",
        lazy="selectin",
        overlaps="role_assignments,user,role",
    )
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    devices: Mapped[list["DeviceModel"]] = relationship(
        "DeviceModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    profile: Mapped[Optional["UserProfileModel"]] = relationship(
        "UserProfileModel",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    role_assignments: Mapped[list["RoleAssignmentModel"]] = relationship(
        "RoleAssignmentModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="roles",
    )
    verification_tokens: Mapped[list["VerificationTokenModel"]] = relationship(
        "VerificationTokenModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    password_reset_tokens: Mapped[list["PasswordResetTokenModel"]] = relationship(
        "PasswordResetTokenModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    audit_logs: Mapped[list["AuditLogModel"]] = relationship(
        "AuditLogModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    login_events: Mapped[list["LoginEventModel"]] = relationship(
        "LoginEventModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    security_events: Mapped[list["SecurityEventModel"]] = relationship(
        "SecurityEventModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserProfileModel(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferred_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    matric_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user: Mapped[UserModel] = relationship("UserModel", back_populates="profile")


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    meta_data: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped[Optional[UserModel]] = relationship(
        "UserModel", back_populates="audit_logs"
    )


class DeviceModel(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String, nullable=False)
    os: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    push_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[UserModel] = relationship("UserModel", back_populates="devices")
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel",
        back_populates="device",
        lazy="selectin",
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[UserModel] = relationship("UserModel", back_populates="sessions")
    device: Mapped[Optional[DeviceModel]] = relationship(
        "DeviceModel", back_populates="sessions"
    )
    refresh_tokens: Mapped[list["RefreshTokenModel"]] = relationship(
        "RefreshTokenModel",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    users: Mapped[list[UserModel]] = relationship(
        "UserModel",
        secondary="role_assignments",
        back_populates="roles",
        lazy="selectin",
        overlaps="role_assignments,user,role",
    )
    permissions: Mapped[list["PermissionModel"]] = relationship(
        "PermissionModel",
        secondary=role_permissions_table,
        back_populates="roles",
        lazy="selectin",
    )
    role_assignments: Mapped[list["RoleAssignmentModel"]] = relationship(
        "RoleAssignmentModel",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="roles,users",
    )


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    roles: Mapped[list[RoleModel]] = relationship(
        "RoleModel",
        secondary=role_permissions_table,
        back_populates="permissions",
        lazy="selectin",
    )


class RoleAssignmentModel(Base):
    __tablename__ = "role_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[UserModel] = relationship(
        "UserModel", back_populates="role_assignments", overlaps="roles,users"
    )
    role: Mapped[RoleModel] = relationship(
        "RoleModel", back_populates="role_assignments", overlaps="roles,users"
    )


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped[SessionModel] = relationship(
        "SessionModel", back_populates="refresh_tokens"
    )


class VerificationTokenModel(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[UserModel] = relationship(
        "UserModel", back_populates="verification_tokens"
    )


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[UserModel] = relationship(
        "UserModel", back_populates="password_reset_tokens"
    )


class LoginEventModel(Base):
    __tablename__ = "login_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    successful: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped[Optional[UserModel]] = relationship(
        "UserModel", back_populates="login_events"
    )
    device: Mapped[Optional[DeviceModel]] = relationship("DeviceModel")


class SecurityEventModel(Base):
    __tablename__ = "security_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    meta_data: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped[Optional[UserModel]] = relationship(
        "UserModel", back_populates="security_events"
    )
