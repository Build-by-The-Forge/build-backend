from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.application.identity.ports.token_service import InvalidTokenError
from app.core.config import Settings
from app.infrastructure.security.jwt_token_service import JWTTokenService

KEY = "k" * 32
OLD_KEY = "o" * 32


def settings(**overrides) -> Settings:
    base = dict(app_environment="testing", auth_jwt_secret=KEY, auth_jwt_kid="current")
    base.update(overrides)
    return Settings(_env_file=None, **base)


def service(**overrides) -> JWTTokenService:
    return JWTTokenService(settings(**overrides))


def forge(claims_overrides=None, *, key=KEY, kid="current", algorithm="HS256", headers=None):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "build-backend",
        "aud": "build-api",
        "sub": "user-1",
        "sid": "session-1",
        "typ": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(claims_overrides or {})
    claims = {k: v for k, v in claims.items() if v is not None}
    hdrs = {"kid": kid} if kid is not None else {}
    hdrs.update(headers or {})
    return jwt.encode(claims, key, algorithm=algorithm, headers=hdrs)


def test_issued_token_round_trips():
    svc = service()
    claims = svc.decode_access_token(svc.issue_access_token("user-1", "session-1"))

    assert (claims.user_id, claims.session_id) == ("user-1", "session-1")
    assert claims.expires_at > datetime.now(timezone.utc)


def test_token_lifetime_comes_from_configuration():
    svc = service(auth_access_token_ttl_seconds=60)
    claims = svc.decode_access_token(svc.issue_access_token("u", "s"))

    remaining = claims.expires_at - datetime.now(timezone.utc)
    assert timedelta(seconds=0) < remaining <= timedelta(seconds=60)


def test_issued_token_carries_kid_and_no_tenant_or_role():
    token = service().issue_access_token("user-1", "session-1")
    payload = jwt.decode(token, options={"verify_signature": False})

    assert jwt.get_unverified_header(token)["kid"] == "current"
    assert not {"tenant_id", "role", "permissions", "membership_id"} & payload.keys()


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda: forge({"exp": datetime.now(timezone.utc) - timedelta(minutes=5)}), id="expired"),
        pytest.param(lambda: forge({"nbf": datetime.now(timezone.utc) + timedelta(minutes=5)}), id="not-yet-valid"),
        pytest.param(lambda: forge({"iss": "someone-else"}), id="wrong-issuer"),
        pytest.param(lambda: forge({"aud": "another-api"}), id="wrong-audience"),
        pytest.param(lambda: forge(key="x" * 32), id="wrong-key"),
        pytest.param(lambda: forge(kid="unknown"), id="unknown-kid"),
        pytest.param(lambda: forge(kid=None), id="missing-kid"),
        pytest.param(lambda: forge(algorithm="HS512"), id="algorithm-swap"),
        pytest.param(lambda: forge({"typ": "refresh"}), id="wrong-type"),
        pytest.param(lambda: forge({"sid": None}), id="missing-session"),
        pytest.param(lambda: forge({"sub": None}), id="missing-subject"),
        pytest.param(lambda: forge({"exp": None}), id="missing-expiry"),
        pytest.param(
            lambda: jwt.encode({"sub": "user-1", "sid": "s", "typ": "access"}, None, algorithm="none"),
            id="alg-none",
        ),
        pytest.param(lambda: "not.a.jwt", id="garbage"),
        pytest.param(lambda: "", id="empty"),
    ],
)
def test_rejected_tokens(token_factory):
    with pytest.raises(InvalidTokenError):
        service().decode_access_token(token_factory())


def test_small_clock_skew_is_tolerated():
    token = forge({"nbf": datetime.now(timezone.utc) + timedelta(seconds=10)})

    assert service().decode_access_token(token).user_id == "user-1"


def test_rotation_accepts_tokens_signed_with_the_previous_key():
    old_token = JWTTokenService(settings(auth_jwt_secret=OLD_KEY, auth_jwt_kid="old")).issue_access_token("user-1", "session-1")
    rotated = service(auth_jwt_previous_secret=OLD_KEY, auth_jwt_previous_kid="old")

    assert rotated.decode_access_token(old_token).user_id == "user-1"


def test_previous_key_is_rejected_once_retired():
    old_token = JWTTokenService(settings(auth_jwt_secret=OLD_KEY, auth_jwt_kid="old")).issue_access_token("user-1", "session-1")

    with pytest.raises(InvalidTokenError):
        service().decode_access_token(old_token)
