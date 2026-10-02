from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.application.identity.ports.password_hasher import PasswordHasher
from app.domain.identity.value_objects import Password, PasswordHash


class Argon2PasswordHasher(PasswordHasher):
    """Argon2id password hashing (argon2-cffi defaults: RFC 9106 low-memory profile)."""

    def __init__(self, argon2: _Argon2 | None = None) -> None:
        self._argon2 = argon2 or _Argon2()
        self._dummy_hash = self._argon2.hash("dummy password for timing equalisation")

    def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(self._argon2.hash(password.value))

    def verify(self, plain_password: Password, stored_hash: PasswordHash) -> bool:
        try:
            return self._argon2.verify(stored_hash.value, plain_password.value)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            # InvalidHashError covers anything that is not an Argon2 hash,
            # including the retired plaintext "hashed:<password>" format.
            return False

    def needs_rehash(self, stored_hash: PasswordHash) -> bool:
        try:
            return self._argon2.check_needs_rehash(stored_hash.value)
        except InvalidHashError:
            return True

    def dummy_verify(self, plain_password: Password) -> None:
        self.verify(plain_password, PasswordHash(self._dummy_hash))
