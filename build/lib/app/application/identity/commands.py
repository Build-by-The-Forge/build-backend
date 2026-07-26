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
