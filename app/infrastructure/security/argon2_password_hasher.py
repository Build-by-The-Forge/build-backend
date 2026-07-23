from app.application.identity.ports.password_hasher import PasswordHasher
from app.domain.identity.value_objects import Password, PasswordHash


class Argon2PasswordHasher(PasswordHasher):
    def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(f"hashed:{password.value}")

    def verify(self, plain_password: Password, stored_hash: PasswordHash) -> bool:
        return self.hash(plain_password).value == stored_hash.value
