from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class InvalidTokenError(Exception):
    """The token is malformed, forged, expired, or otherwise not acceptable."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: str
    session_id: str
    expires_at: datetime


class TokenService(Protocol):
    def issue_access_token(self, user_id: str, session_id: str) -> str:
        raise NotImplementedError

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Verify and decode an access token; raise InvalidTokenError otherwise."""
        raise NotImplementedError
