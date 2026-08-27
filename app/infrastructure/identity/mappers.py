from datetime import datetime, timezone

from app.domain.identity.user import RefreshToken, Session, User
from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    PasswordHash,
    RefreshTokenHash,
    RefreshTokenId,
    SessionId,
    UserId,
)
from app.infrastructure.identity.models import (
    RefreshTokenModel,
    SessionModel,
    UserModel,
)


def user_model_to_domain(model: UserModel) -> User:
    if model is None:
        return User(id=UserId(""), email=Email(""), password_hash=PasswordHash(""))

    return User(
        id=UserId(model.id),
        email=Email(model.email),
        password_hash=PasswordHash(model.password_hash),
        is_active=model.is_active,
        created_at=model.created_at,
        roles=[],
    )


def domain_user_to_model(user: User, model: UserModel | None = None) -> UserModel:
    created_at = user.created_at or datetime.now(timezone.utc)
    if model is None:
        model = UserModel(
            id=user.id.value,
            email=user.email.value,
            password_hash=user.password_hash.value,
            is_active=user.is_active,
            created_at=created_at,
        )
    else:
        model.email = user.email.value
        model.password_hash = user.password_hash.value
        model.is_active = user.is_active
        model.created_at = created_at
    return model


def session_model_to_domain(model: SessionModel) -> Session:
    return Session(
        id=SessionId(model.id),
        user_id=UserId(model.user_id),
        device_id=DeviceId(model.device_id) if model.device_id else None,
        refresh_token_hash=(
            RefreshTokenHash(model.refresh_token_hash)
            if model.refresh_token_hash
            else None
        ),
        ip_address=model.ip_address,
        user_agent=model.user_agent,
        created_at=model.created_at,
        expires_at=model.expires_at,
        last_seen_at=model.last_seen_at,
        revoked_at=model.revoked_at,
    )


def domain_session_to_model(
    session: Session, model: SessionModel | None = None
) -> SessionModel:
    created_at = session.created_at or datetime.now(timezone.utc)
    last_seen_at = session.last_seen_at or created_at
    if model is None:
        model = SessionModel(
            id=session.id.value,
            user_id=session.user_id.value,
            device_id=session.device_id.value if session.device_id else None,
            refresh_token_hash=(
                session.refresh_token_hash.value if session.refresh_token_hash else None
            ),
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            created_at=created_at,
            expires_at=session.expires_at,
            last_seen_at=last_seen_at,
            revoked_at=session.revoked_at,
        )
    else:
        model.user_id = session.user_id.value
        model.device_id = session.device_id.value if session.device_id else None
        model.refresh_token_hash = (
            session.refresh_token_hash.value if session.refresh_token_hash else None
        )
        model.ip_address = session.ip_address
        model.user_agent = session.user_agent
        model.created_at = created_at
        model.expires_at = session.expires_at
        model.last_seen_at = last_seen_at
        model.revoked_at = session.revoked_at
    return model


def refresh_token_model_to_domain(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=RefreshTokenId(model.id),
        session_id=SessionId(model.session_id),
        token_hash=RefreshTokenHash(model.token_hash),
        expires_at=model.expires_at,
        rotated_at=model.rotated_at,
        revoked_at=model.revoked_at,
    )
