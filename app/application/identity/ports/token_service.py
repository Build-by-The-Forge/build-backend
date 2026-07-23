from typing import Protocol


class TokenService(Protocol):
    def issue_access_token(self, subject: str) -> str:
        raise NotImplementedError

    def issue_refresh_token(self, subject: str) -> str:
        raise NotImplementedError

    def decode(self, token: str) -> dict[str, str]:
        raise NotImplementedError

    def validate(self, token: str) -> bool:
        raise NotImplementedError
