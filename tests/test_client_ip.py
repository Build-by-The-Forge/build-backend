"""Client address behind trusted proxies (plan §8.4 proxy behaviour, M6)."""

import ipaddress

import pytest

from app.core.config import Settings
from app.core.request_context import resolve_client_ip

PROXIES = [ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("192.0.2.10/32")]


@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        ("203.0.113.5", None, "203.0.113.5"),  # direct client
        ("203.0.113.5", "1.2.3.4", "203.0.113.5"),  # untrusted peer: header ignored
        ("10.1.1.1", "198.51.100.7", "198.51.100.7"),  # one trusted proxy
        ("10.1.1.1", "1.2.3.4, 198.51.100.7, 192.0.2.10", "198.51.100.7"),  # spoofed left part ignored
        ("10.1.1.1", "10.2.2.2, 10.3.3.3", "10.1.1.1"),  # only proxies: the peer
        ("10.1.1.1", "not-an-ip", "10.1.1.1"),  # malformed: the peer
        ("10.1.1.1", None, "10.1.1.1"),
    ],
)
def test_resolve_client_ip(peer, forwarded, expected):
    assert resolve_client_ip(peer, forwarded, PROXIES) == expected


def test_without_trusted_proxies_the_header_is_never_read():
    assert resolve_client_ip("10.1.1.1", "198.51.100.7", []) == "10.1.1.1"


def test_trusted_proxies_are_validated():
    base = {"ai_service_url": "http://ai:8000"}
    assert len(Settings(_env_file=None, trusted_proxies="10.0.0.0/8, 192.0.2.10", **base).trusted_proxy_networks) == 2
    with pytest.raises(ValueError, match="TRUSTED_PROXIES"):
        Settings(_env_file=None, trusted_proxies="10.0.0.0/8, proxy.local", **base)
