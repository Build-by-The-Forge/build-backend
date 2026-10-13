"""Per-request metadata available to code that has no Request object
(for example the security-event recorder)."""

import ipaddress
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class RequestMeta:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


current_request: ContextVar[RequestMeta] = ContextVar("current_request", default=RequestMeta())


def client_ip(request: Request) -> str:
    """The client address used for rate limits and security events.

    The direct peer, unless the peer is a configured trusted proxy: then the
    X-Forwarded-For chain is read from the right, skipping trusted proxies,
    and the first other address is the client. A client cannot choose its
    address by sending the header itself, because only a trusted peer's
    header is read.
    """
    peer = request.client.host if request.client else "unknown"
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), settings.trusted_proxy_networks)


def _is_trusted(address: str, networks: list) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def resolve_client_ip(peer: str, forwarded_for: str | None, networks: list) -> str:
    if not networks or not forwarded_for or not _is_trusted(peer, networks):
        return peer
    for hop in reversed([h.strip() for h in forwarded_for.split(",") if h.strip()]):
        if not _is_trusted(hop, networks):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer  # malformed chain: fall back to the peer
    return peer
