from app.application.identity.ports.token_service import TokenService


class JWTTokenService(TokenService):
    def issue_access_token(self, subject: str) -> str:
        return f"access:{subject}"

    def issue_refresh_token(self, subject: str) -> str:
        return f"refresh:{subject}"

    def decode(self, token: str) -> dict[str, str]:
        return {"sub": token}

    def validate(self, token: str) -> bool:
        return bool(token)
