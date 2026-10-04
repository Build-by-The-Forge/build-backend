from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    session_id: str
    # Decision D4: unverified accounts may sign in, but get no tenant access.
    email_verified: bool = False
