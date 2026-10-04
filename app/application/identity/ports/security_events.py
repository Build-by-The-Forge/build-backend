from enum import Enum
from typing import Any, Protocol


class SecurityEvent(tuple[str, str], Enum):
    """(event_type, action) pairs written to security_events."""

    ACCOUNT_REGISTERED = ("account", "registered")
    EMAIL_VERIFIED = ("email", "verified")
    PASSWORD_RESET_REQUESTED = ("password", "reset_requested")
    PASSWORD_RESET_COMPLETED = ("password", "reset_completed")
    PASSWORD_CHANGED = ("password", "changed")
    PASSWORD_CHANGE_FAILED = ("password", "change_failed")
    REFRESH_TOKEN_REUSE = ("session", "refresh_token_reuse_detected")
    LOGOUT = ("session", "logout")
    LOGOUT_ALL = ("session", "logout_all")
    SIGN_IN_TEMPORARILY_LOCKED = ("auth", "temporary_lock")
    ACCOUNT_PROVISIONED = ("account", "provisioned")
    TENANT_OWNER_GRANTED = ("membership", "owner_granted")
    INVITATION_CREATED = ("invitation", "created")
    INVITATION_REVOKED = ("invitation", "revoked")
    INVITATION_ACCEPTED = ("invitation", "accepted")
    MEMBERSHIP_ROLE_CHANGED = ("membership", "role_changed")
    MEMBERSHIP_REVOKED = ("membership", "revoked")
    MEMBERSHIP_REACTIVATED = ("membership", "reactivated")
    MEMBERSHIP_JOINED_BY_EMAIL_DOMAIN = ("membership", "joined_by_email_domain")
    TENANT_JOIN_POLICY_UPDATED = ("tenant", "join_policy_updated")


class LoginFailureReason(str, Enum):
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_NOT_ACTIVE = "account_not_active"
    RATE_LIMITED = "rate_limited"


class SecurityEventRecorder(Protocol):
    """Append-only security audit trail.

    Implementations must never raise: a failure to record is logged and the
    request continues. Never pass secrets (passwords, tokens, codes) in
    ``metadata``.
    """

    async def record(
        self,
        event: SecurityEvent,
        *,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def record_login(
        self,
        *,
        user_id: str | None,
        successful: bool,
        reason: LoginFailureReason | None = None,
    ) -> None: ...
