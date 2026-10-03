from dataclasses import dataclass


@dataclass(slots=True)
class RegisterUserCommand:
    email: str
    password: str


@dataclass(slots=True)
class AuthenticateUserCommand:
    email: str
    password: str
    device_id: str | None = None
    user_agent: str | None = None


@dataclass(slots=True)
class RefreshSessionCommand:
    refresh_token: str


@dataclass(slots=True)
class LogoutSessionCommand:
    session_id: str
    user_id: str


@dataclass(slots=True)
class LogoutAllSessionsCommand:
    user_id: str


@dataclass(slots=True)
class ForgotPasswordCommand:
    email: str


@dataclass(slots=True)
class ResetPasswordCommand:
    token: str
    password: str


@dataclass(slots=True)
class GetCurrentUserCommand:
    user_id: str
