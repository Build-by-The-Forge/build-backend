from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.application.identity.ports.token_service import (
    AccessTokenClaims,
    InvalidTokenError,
    TokenService,
)
from app.core.config import Settings
from app.core.config import settings as default_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
CLOCK_LEEWAY_SECONDS = 30


class JWTTokenService(TokenService):
    """HS256 access tokens. They identify a user and session only; tenant,
    membership and role are resolved from the database on every request."""

    def __init__(self, config: Settings | None = None) -> None:
        self._config = config or default_settings

    def issue_access_token(self, user_id: str, session_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iss": self._config.auth_jwt_issuer,
            "aud": self._config.auth_jwt_audience,
            "sub": user_id,
            "sid": session_id,
            "typ": ACCESS_TOKEN_TYPE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=self._config.auth_access_token_ttl_seconds),
            "jti": str(uuid4()),
        }
        return jwt.encode(
            payload,
            self._config.auth_jwt_secret,
            algorithm=ALGORITHM,
            headers={"kid": self._config.auth_jwt_kid},
        )

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("malformed token") from exc

        key = self._config.jwt_verification_keys.get(kid) if isinstance(kid, str) else None
        if key is None:
            raise InvalidTokenError("unknown signing key")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],  # pinned: rejects "none" and algorithm swaps
                audience=self._config.auth_jwt_audience,
                issuer=self._config.auth_jwt_issuer,
                leeway=CLOCK_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        user_id, session_id = claims.get("sub"), claims.get("sid")
        if claims.get("typ") != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("not an access token")
        if not isinstance(user_id, str) or not user_id:
            raise InvalidTokenError("missing subject")
        if not isinstance(session_id, str) or not session_id:
            raise InvalidTokenError("missing session")

        return AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )
