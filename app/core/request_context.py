"""Per-request metadata available to code that has no Request object
(for example the security-event recorder)."""

from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True, slots=True)
class RequestMeta:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


current_request: ContextVar[RequestMeta] = ContextVar(
    "current_request", default=RequestMeta()
)


def client_ip(request: Request) -> str:
    # The direct peer. Behind a reverse proxy this must become the
    # proxy-reported client address from a trusted proxy chain (M6).
    return request.client.host if request.client else "unknown"
