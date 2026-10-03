import hashlib

import pytest
from argon2 import PasswordHasher as Argon2

from app.application.identity.commands import (
    AuthenticateUserCommand,
    ForgotPasswordCommand,
    ResetPasswordCommand,
)
from app.application.identity.handlers import (
    AuthenticateUserHandler,
    ForgotPasswordHandler,
    ResetPasswordHandler,
)
from app.core.exceptions import AppError
from app.domain.identity.user import User
from app.domain.identity.value_objects import Email, Password, UserId
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService

EMAIL = "student@futa.edu.ng"
PASSWORD = "CorrectHorse-Battery-9"


class SpyHasher(Argon2PasswordHasher):
    def __init__(self, argon2=None):
        super().__init__(argon2)
        self.dummy_calls = 0

    def dummy_verify(self, plain_password):
        self.dummy_calls += 1
        super().dummy_verify(plain_password)


class FakeUsers:
    def __init__(self, user: User | None = None):
        self.user = user
        self.saved: list[User] = []
        self.reset_tokens: dict[str, str] = {}

    async def get_by_email(self, email):
        return self.user if self.user and self.user.email.value == email else None

    async def get_by_id(self, user_id):
        return self.user if self.user and self.user.id.value == user_id else None

    async def save(self, user):
        self.saved.append(user)
        return user

    async def save_password_reset_token(self, user_id, token_hash, expires_at=None):
        self.reset_tokens[token_hash] = user_id

    async def consume_password_reset_token(self, token_hash):
        return self.reset_tokens.pop(token_hash, None)

    async def invalidate_password_reset_tokens(self, user_id):
        self.reset_tokens = {h: u for h, u in self.reset_tokens.items() if u != user_id}


def make_user(hasher) -> User:
    return User(
        id=UserId(""),
        email=Email(EMAIL),
        password_hash=hasher.hash(Password(PASSWORD)),
    )


def handler(repo, hasher):
    return AuthenticateUserHandler(
        repository=repo, password_hasher=hasher, token_service=JWTTokenService()
    )


async def test_unknown_email_is_rejected_after_a_dummy_verification():
    hasher = SpyHasher()

    with pytest.raises(AppError) as exc:
        await handler(FakeUsers(), hasher).handle(
            AuthenticateUserCommand(email=EMAIL, password=PASSWORD)
        )

    assert exc.value.status_code == 401
    assert hasher.dummy_calls == 1


async def test_wrong_password_is_rejected_without_a_dummy_verification():
    hasher = SpyHasher()
    repo = FakeUsers(make_user(hasher))

    with pytest.raises(AppError) as exc:
        await handler(repo, hasher).handle(
            AuthenticateUserCommand(email=EMAIL, password="WrongHorse-Battery-9")
        )

    assert exc.value.status_code == 401
    assert hasher.dummy_calls == 0


@pytest.mark.parametrize(
    "email,password",
    [
        ("not-an-email", PASSWORD),
        (EMAIL, "short"),  # invalid format for an existing account
        ("unknown@futa.edu.ng", "short"),  # ...and for an unknown one
    ],
)
async def test_invalid_input_fails_like_bad_credentials(email, password):
    hasher = SpyHasher()
    repo = FakeUsers(make_user(hasher))

    with pytest.raises(AppError) as exc:
        await handler(repo, hasher).handle(
            AuthenticateUserCommand(email=email, password=password)
        )

    assert exc.value.status_code == 401
    assert str(exc.value) == "invalid credentials"


async def test_successful_login_upgrades_an_outdated_hash():
    weak = Argon2PasswordHasher(Argon2(time_cost=1, memory_cost=8, parallelism=1))
    current = Argon2PasswordHasher()
    user = make_user(weak)
    repo = FakeUsers(user)

    await handler(repo, current).handle(
        AuthenticateUserCommand(email=EMAIL, password=PASSWORD)
    )

    assert repo.saved == [user]
    assert not current.needs_rehash(user.password_hash)
    assert current.verify(Password(PASSWORD), user.password_hash)


async def test_successful_login_with_current_hash_does_not_rewrite_it():
    hasher = Argon2PasswordHasher()
    repo = FakeUsers(make_user(hasher))

    await handler(repo, hasher).handle(
        AuthenticateUserCommand(email=EMAIL, password=PASSWORD)
    )

    assert repo.saved == []


async def test_reset_token_is_stored_only_as_sha256_and_resets_the_password():
    hasher = Argon2PasswordHasher()
    user = make_user(hasher)
    repo = FakeUsers(user)

    request = await ForgotPasswordHandler(repo).handle(ForgotPasswordCommand(email=EMAIL))
    raw = request.raw_token

    assert raw not in repo.reset_tokens
    assert list(repo.reset_tokens) == [hashlib.sha256(raw.encode()).hexdigest()]

    new_password = "BrandNew-Passphrase-42"
    await ResetPasswordHandler(repo, hasher).handle(
        ResetPasswordCommand(token=raw, password=new_password)
    )

    assert hasher.verify(Password(new_password), user.password_hash)
    assert repo.reset_tokens == {}
