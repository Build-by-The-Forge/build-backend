"""BUILD Service Signature v1 (docs/phase1-m3-boundary-design.md, Part A).

Pure protocol code: canonical request, canonical context, signing and
verification. It knows nothing about HTTP frameworks, Redis or settings; the
request-body limit and the replay check (A.5 steps 6 and 8) wrap it.

AI-service implements the same protocol independently. Test vector A.7, not
shared code, proves that both compute the same signature.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from app.infrastructure.security.service_context import (
    InvalidServiceContext,
    ServiceContext,
)

VERSION = "v1"

HEADER_SERVICE = "X-BUILD-Service"
HEADER_TIMESTAMP = "X-BUILD-Timestamp"
HEADER_REQUEST_ID = "X-BUILD-Request-ID"
HEADER_CONTEXT = "X-BUILD-Context"
HEADER_SIGNATURE = "X-BUILD-Signature"
SIGNED_HEADERS = (
    HEADER_SERVICE,
    HEADER_TIMESTAMP,
    HEADER_REQUEST_ID,
    HEADER_CONTEXT,
    HEADER_SIGNATURE,
)

TIMESTAMP_WINDOW_SECONDS = 60
MAX_CONTEXT_HEADER_CHARS = 4096
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()

_SIGNATURE_RE = re.compile(r"v1=[0-9a-f]{64}")
_TIMESTAMP_RE = re.compile(r"[1-9][0-9]{0,11}")
_UUID4_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_BASE64URL_RE = re.compile(r"[A-Za-z0-9_-]*")


class Direction(Enum):
    """Each direction has its own sender id and its own secret (A.1)."""

    BACKEND_TO_AI = "build-backend"
    AI_TO_BACKEND = "ai-service"

    @property
    def sender(self) -> str:
        return self.value


@dataclass(frozen=True)
class ServiceKeys:
    """One direction's secrets. Signers use only ``current``; receivers also
    accept ``previous`` while a rotation is in progress."""

    current: str
    previous: str | None = None

    @property
    def verification_secrets(self) -> tuple[str, ...]:
        return (self.current,) if not self.previous else (self.current, self.previous)


@dataclass(frozen=True)
class VerifiedServiceRequest:
    service: str
    timestamp: int
    request_id: str
    context: ServiceContext
    context_bytes: bytes


class ServiceAuthError(Exception):
    """Verification failed. ``reason`` is for internal logs only; callers
    answer every cause with the same 401 (A.5)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_context_bytes(context: Mapping[str, Any]) -> bytes:
    return json.dumps(
        context, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def encode_context(context: Mapping[str, Any]) -> str:
    return (
        base64.urlsafe_b64encode(canonical_context_bytes(context))
        .rstrip(b"=")
        .decode("ascii")
    )


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def decode_context(header: str) -> tuple[bytes, dict[str, Any]]:
    """Decode the context header and require its canonical encoding.

    The field schema (A.4 table) is enforced on top of this by the context
    contract; here the header must be unpadded base64url of a JSON object
    that re-serialises byte-identically.
    """
    if len(header) > MAX_CONTEXT_HEADER_CHARS:
        raise ServiceAuthError("context header too long")
    if not _BASE64URL_RE.fullmatch(header) or len(header) % 4 == 1:
        raise ServiceAuthError("context header is not unpadded base64url")
    try:
        raw = base64.urlsafe_b64decode(header + "=" * (-len(header) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ServiceAuthError("context header is not base64url") from exc
    # Unused trailing bits would give one context several header spellings.
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != header:
        raise ServiceAuthError("context header is not canonical base64url")

    try:
        context = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise ServiceAuthError("context is not ASCII JSON") from exc
    if not isinstance(context, dict):
        raise ServiceAuthError("context is not a JSON object")
    if canonical_context_bytes(context) != raw:
        raise ServiceAuthError("context is not canonical JSON")
    return raw, context


def request_target(raw_path: bytes, query_string: bytes) -> str:
    """The request target exactly as sent: raw path, plus ``?query`` when the
    query is non-empty. Never decoded, normalised or reordered (A.3)."""
    try:
        path = raw_path.decode("ascii")
        query = query_string.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ServiceAuthError("request target is not ASCII") from exc
    return f"{path}?{query}" if query else path


def canonical_request(
    *,
    service: str,
    method: str,
    target: str,
    timestamp: str,
    request_id: str,
    body_sha256: str,
    context_sha256: str,
) -> bytes:
    return "\n".join(
        (
            VERSION,
            service,
            method.upper(),
            target,
            timestamp,
            request_id,
            body_sha256,
            context_sha256,
        )
    ).encode("utf-8")


def compute_signature(secret: str, canonical: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return f"{VERSION}={digest}"


def sign_request(
    *,
    direction: Direction,
    keys: ServiceKeys,
    method: str,
    target: str,
    body: bytes,
    context: ServiceContext,
    timestamp: int,
    request_id: str | None = None,
) -> dict[str, str]:
    """Return the five signed headers for one outgoing request."""
    request_id = request_id or str(uuid4())
    context_body = context.to_dict()
    context_header = encode_context(context_body)
    canonical = canonical_request(
        service=direction.sender,
        method=method,
        target=target,
        timestamp=str(timestamp),
        request_id=request_id,
        body_sha256=sha256_hex(body),
        context_sha256=sha256_hex(canonical_context_bytes(context_body)),
    )
    return {
        HEADER_SERVICE: direction.sender,
        HEADER_TIMESTAMP: str(timestamp),
        HEADER_REQUEST_ID: request_id,
        HEADER_CONTEXT: context_header,
        HEADER_SIGNATURE: compute_signature(keys.current, canonical),
    }


def _signed_headers(headers: Mapping[str, str]) -> dict[str, str]:
    wanted = {name.lower(): name for name in SIGNED_HEADERS}
    found: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        if key in wanted:
            if key in found:
                raise ServiceAuthError(f"duplicate {wanted[key]} header")
            found[key] = value
    missing = [wanted[key] for key in wanted if key not in found]
    if missing:
        raise ServiceAuthError(f"missing headers: {', '.join(missing)}")
    return {wanted[key]: value for key, value in found.items()}


def verify_request(
    *,
    direction: Direction,
    keys: ServiceKeys,
    method: str,
    target: str,
    headers: Mapping[str, str],
    body_sha256: str,
    now: int,
) -> VerifiedServiceRequest:
    """A.5 steps 1-5 and 7, in order. ``direction`` is the direction this
    receiver accepts; ``body_sha256`` is computed while the body is read."""
    values = _signed_headers(headers)
    signature = values[HEADER_SIGNATURE]
    if not _SIGNATURE_RE.fullmatch(signature):
        raise ServiceAuthError("malformed signature header")

    service = values[HEADER_SERVICE]
    if service != direction.sender:
        raise ServiceAuthError("unexpected sender")

    timestamp = values[HEADER_TIMESTAMP]
    if not _TIMESTAMP_RE.fullmatch(timestamp):
        raise ServiceAuthError("malformed timestamp")
    if abs(now - int(timestamp)) > TIMESTAMP_WINDOW_SECONDS:
        raise ServiceAuthError("timestamp outside window")

    request_id = values[HEADER_REQUEST_ID]
    if not _UUID4_RE.fullmatch(request_id):
        raise ServiceAuthError("request id is not a canonical UUIDv4")

    context_bytes, decoded = decode_context(values[HEADER_CONTEXT])
    try:
        context = ServiceContext.from_dict(decoded)
    except InvalidServiceContext as exc:
        raise ServiceAuthError(f"invalid context: {exc}") from exc

    canonical = canonical_request(
        service=service,
        method=method,
        target=target,
        timestamp=timestamp,
        request_id=request_id,
        body_sha256=body_sha256,
        context_sha256=sha256_hex(context_bytes),
    )
    if not any(
        hmac.compare_digest(compute_signature(secret, canonical), signature)
        for secret in keys.verification_secrets
    ):
        raise ServiceAuthError("signature mismatch")

    return VerifiedServiceRequest(
        service=service,
        timestamp=int(timestamp),
        request_id=request_id,
        context=context,
        context_bytes=context_bytes,
    )
