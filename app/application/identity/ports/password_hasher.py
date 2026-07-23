from typing import Protocol

from app.domain.identity.value_objects import Password, PasswordHash


class PasswordHasher(Protocol):
    def hash(self, password: Password) -> PasswordHash:
        raise NotImplementedError

    def verify(self, plain_password: Password, stored_hash: PasswordHash) -> bool:
        raise NotImplementedError
