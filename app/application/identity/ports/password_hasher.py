from typing import Protocol

from app.domain.identity.value_objects import Password, PasswordHash


class PasswordHasher(Protocol):
    def hash(self, password: Password) -> PasswordHash:
        raise NotImplementedError

    def verify(self, plain_password: Password, stored_hash: PasswordHash) -> bool:
        raise NotImplementedError

    def needs_rehash(self, stored_hash: PasswordHash) -> bool:
        """True when the stored hash uses outdated parameters."""
        raise NotImplementedError

    def dummy_verify(self, plain_password: Password) -> None:
        """Do a verification of equal cost to a real one, discarding the result.

        Used when the account does not exist, so response time does not reveal it.
        """
        raise NotImplementedError
