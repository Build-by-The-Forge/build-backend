import pytest
from argon2 import PasswordHasher as Argon2

from app.domain.identity.value_objects import Password, PasswordHash
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher

PASSWORD = Password("CorrectHorse-Battery-9")


def test_hash_is_argon2id_and_never_contains_the_password():
    hashed = Argon2PasswordHasher().hash(PASSWORD)

    assert hashed.value.startswith("$argon2id$")
    assert PASSWORD.value not in hashed.value


def test_hashes_are_salted():
    hasher = Argon2PasswordHasher()

    assert hasher.hash(PASSWORD).value != hasher.hash(PASSWORD).value


def test_verify_accepts_correct_and_rejects_wrong_password():
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash(PASSWORD)

    assert hasher.verify(PASSWORD, hashed)
    assert not hasher.verify(Password("WrongHorse-Battery-9"), hashed)


@pytest.mark.parametrize(
    "stored",
    [
        f"hashed:{PASSWORD.value}",  # retired plaintext format
        PASSWORD.value,  # raw plaintext
        "",
        "$argon2id$garbage",
    ],
)
def test_verify_rejects_anything_that_is_not_a_valid_argon2_hash(stored):
    assert not Argon2PasswordHasher().verify(PASSWORD, PasswordHash(stored))


def test_needs_rehash_detects_outdated_parameters():
    weak = Argon2PasswordHasher(Argon2(time_cost=1, memory_cost=8, parallelism=1))
    current = Argon2PasswordHasher()

    assert current.needs_rehash(weak.hash(PASSWORD))
    assert not current.needs_rehash(current.hash(PASSWORD))
    assert current.needs_rehash(PasswordHash(f"hashed:{PASSWORD.value}"))


def test_dummy_verify_does_not_raise():
    Argon2PasswordHasher().dummy_verify(PASSWORD)


@pytest.mark.parametrize("length,ok", [(11, False), (12, True), (128, True), (129, False)])
def test_password_length_bounds(length, ok):
    if ok:
        Password("x" * length)
    else:
        with pytest.raises(ValueError):
            Password("x" * length)
