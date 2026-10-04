"""BUILD Service Signature v1: test vector A.7, negative vectors and the
verification steps of A.5 that do not need Redis or a request body stream."""

import base64

import pytest
from app.infrastructure.security.service_signature import (
    EMPTY_BODY_SHA256,
    HEADER_CONTEXT,
    HEADER_REQUEST_ID,
    HEADER_SERVICE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    SIGNED_HEADERS,
    Direction,
    ServiceAuthError,
    ServiceKeys,
    canonical_context_bytes,
    canonical_request,
    compute_signature,
    decode_context,
    encode_context,
    request_target,
    sha256_hex,
    sign_request,
    verify_request,
)

# --- Test vector A.7 (docs/phase1-m3-boundary-design.md), verbatim. ---
SECRET = "test-only-backend-to-ai-secret-0123456789abcdef"
SERVICE = "build-backend"
METHOD = "POST"
TARGET = "/v1/ai/generate-questions?lang=en"
TIMESTAMP = "1760000000"
REQUEST_ID = "3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e10"
BODY = b'{"topic":"Thermodynamics","count":5}'
CONTEXT_JSON = (
    b'{"actor":"user","correlation_id":"corr-001",'
    b'"membership_id":"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",'
    b'"permissions":["ai.questions.generate"],"role":"lecturer",'
    b'"tenant_id":"6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c",'
    b'"user_id":"0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d","v":1}'
)
CONTEXT_HEADER = (
    "eyJhY3RvciI6InVzZXIiLCJjb3JyZWxhdGlvbl9pZCI6ImNvcnItMDAxIiwibWVtYmVyc2hpcF9pZCI6"
    "ImExYjJjM2Q0LWU1ZjYtNGE3Yi04YzlkLTBlMWYyYTNiNGM1ZCIsInBlcm1pc3Npb25zIjpbImFpLnF1"
    "ZXN0aW9ucy5nZW5lcmF0ZSJdLCJyb2xlIjoibGVjdHVyZXIiLCJ0ZW5hbnRfaWQiOiI2ZjFjMmE3ZS00"
    "YjNkLTRjOGUtOWExZi0yZDNlNGY1YTZiN2MiLCJ1c2VyX2lkIjoiMGI5ZDhjN2EtNmU1Zi00YTNiLThj"
    "MmQtMWUwZjlhOGI3YzZkIiwidiI6MX0"
)
BODY_SHA256 = "7c60810327978fdb8394acfbccc7e2287850b1309330d9cb3cda5bae3c4aa70d"
CONTEXT_SHA256 = "bd5bf4d02c7c63f22a40f52b497eab2ea1078fa1155956c81c111830fc2d5e06"
CANONICAL = (
    "v1\nbuild-backend\nPOST\n/v1/ai/generate-questions?lang=en\n1760000000\n"
    "3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e10\n"
    "7c60810327978fdb8394acfbccc7e2287850b1309330d9cb3cda5bae3c4aa70d\n"
    "bd5bf4d02c7c63f22a40f52b497eab2ea1078fa1155956c81c111830fc2d5e06"
)
SIGNATURE = "v1=be014f19af31ec051f99db00598a19eb80bc4de18d517f408d2abaca2f719f19"

CONTEXT = {
    "v": 1,
    "actor": "user",
    "tenant_id": "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c",
    "user_id": "0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d",
    "membership_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "role": "lecturer",
    "permissions": ["ai.questions.generate"],
    "correlation_id": "corr-001",
}
KEYS = ServiceKeys(current=SECRET)
NOW = int(TIMESTAMP)


def _vector_headers(**overrides: str) -> dict[str, str]:
    headers = {
        HEADER_SERVICE: SERVICE,
        HEADER_TIMESTAMP: TIMESTAMP,
        HEADER_REQUEST_ID: REQUEST_ID,
        HEADER_CONTEXT: CONTEXT_HEADER,
        HEADER_SIGNATURE: SIGNATURE,
    }
    headers.update(overrides)
    return headers


def _verify(
    headers: dict[str, str] | None = None,
    *,
    method: str = METHOD,
    target: str = TARGET,
    body: bytes = BODY,
    keys: ServiceKeys = KEYS,
    direction: Direction = Direction.BACKEND_TO_AI,
    now: int = NOW,
):
    return verify_request(
        direction=direction,
        keys=keys,
        method=method,
        target=target,
        headers=_vector_headers() if headers is None else headers,
        body_sha256=sha256_hex(body),
        now=now,
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# --- C1: the vector ---------------------------------------------------------


def test_vector_intermediate_values() -> None:
    assert canonical_context_bytes(CONTEXT) == CONTEXT_JSON
    assert encode_context(CONTEXT) == CONTEXT_HEADER
    assert sha256_hex(BODY) == BODY_SHA256
    assert sha256_hex(CONTEXT_JSON) == CONTEXT_SHA256
    assert (
        canonical_request(
            service=SERVICE,
            method=METHOD,
            target=TARGET,
            timestamp=TIMESTAMP,
            request_id=REQUEST_ID,
            body_sha256=BODY_SHA256,
            context_sha256=CONTEXT_SHA256,
        )
        == CANONICAL.encode("ascii")
    )


def test_vector_signature() -> None:
    assert compute_signature(SECRET, CANONICAL.encode("ascii")) == SIGNATURE


def test_sign_request_reproduces_the_vector_headers() -> None:
    headers = sign_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method=METHOD,
        target=TARGET,
        body=BODY,
        context=CONTEXT,
        timestamp=NOW,
        request_id=REQUEST_ID,
    )
    assert headers == _vector_headers()


def test_vector_verifies() -> None:
    verified = _verify()
    assert verified.service == SERVICE
    assert verified.timestamp == NOW
    assert verified.request_id == REQUEST_ID
    assert verified.context == CONTEXT
    assert verified.context_bytes == CONTEXT_JSON


# --- C1: negative vectors: any single change alters the signature ----------

_MUTATIONS = {
    "service": {"service": "ai-service"},
    "method": {"method": "PUT"},
    "path": {"target": "/v1/ai/generate-question?lang=en"},
    "query": {"target": "/v1/ai/generate-questions?lang=fr"},
    "query added": {"target": "/v1/ai/generate-questions?lang=en&count=50"},
    "query removed": {"target": "/v1/ai/generate-questions"},
    "timestamp": {"timestamp": "1760000001"},
    "request id": {"request_id": "3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e11"},
    "body": {"body_sha256": sha256_hex(b'{"topic":"Thermodynamics","count":6}')},
    "context": {
        "context_sha256": sha256_hex(
            CONTEXT_JSON.replace(b"6f1c2a7e-4b3d", b"6f1c2a7e-4b3e")
        )
    },
}


@pytest.mark.parametrize("field", list(_MUTATIONS))
def test_each_single_field_change_alters_the_signature(field: str) -> None:
    fields = {
        "service": SERVICE,
        "method": METHOD,
        "target": TARGET,
        "timestamp": TIMESTAMP,
        "request_id": REQUEST_ID,
        "body_sha256": BODY_SHA256,
        "context_sha256": CONTEXT_SHA256,
    }
    fields.update(_MUTATIONS[field])
    assert compute_signature(SECRET, canonical_request(**fields)) != SIGNATURE


def test_a_different_secret_alters_the_signature() -> None:
    assert compute_signature(SECRET + "x", CANONICAL.encode("ascii")) != SIGNATURE


# --- The same changes are refused by the verifier --------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "PUT"},
        {"target": "/v1/ai/generate-question?lang=en"},
        {"target": "/v1/ai/generate-questions?lang=fr"},
        {"target": "/v1/ai/generate-questions?lang=en&count=50"},
        {"target": "/v1/ai/generate-questions"},
        {"body": b'{"topic":"Thermodynamics","count":6}'},
        {"body": b""},
    ],
    ids=["method", "path", "query", "query-added", "query-removed", "body", "body-empty"],
)
def test_verifier_refuses_a_changed_request(kwargs) -> None:
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(**kwargs)


@pytest.mark.parametrize("field", ["tenant_id", "user_id", "permissions"])
def test_verifier_refuses_a_swapped_context(field: str) -> None:
    swapped = dict(CONTEXT)
    swapped[field] = (
        ["ai.use"] if field == "permissions" else "11111111-2222-4333-8444-555555555555"
    )
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(_vector_headers(**{HEADER_CONTEXT: encode_context(swapped)}))


def test_verifier_refuses_a_changed_timestamp_or_request_id() -> None:
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(_vector_headers(**{HEADER_TIMESTAMP: "1760000001"}))
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(
            _vector_headers(**{HEADER_REQUEST_ID: "3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e11"})
        )


# --- Directions and secrets -------------------------------------------------


def test_receiver_accepts_only_its_directions_sender() -> None:
    # AI-service's verifier for backend requests refuses a claimed "ai-service".
    with pytest.raises(ServiceAuthError, match="unexpected sender"):
        _verify(_vector_headers(**{HEADER_SERVICE: "ai-service"}))
    # The backend's verifier for callbacks refuses a backend-signed request.
    with pytest.raises(ServiceAuthError, match="unexpected sender"):
        _verify(direction=Direction.AI_TO_BACKEND)


def test_a_request_signed_with_the_other_directions_secret_is_refused() -> None:
    other = "test-only-ai-to-backend-secret-fedcba9876543210"
    headers = sign_request(
        direction=Direction.AI_TO_BACKEND,
        keys=ServiceKeys(current=other),
        method="POST",
        target="/content/ingestion/callbacks",
        body=b"{}",
        context=CONTEXT,
        timestamp=NOW,
    )
    verify_request(
        direction=Direction.AI_TO_BACKEND,
        keys=ServiceKeys(current=other),
        method="POST",
        target="/content/ingestion/callbacks",
        headers=headers,
        body_sha256=sha256_hex(b"{}"),
        now=NOW,
    )
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        verify_request(
            direction=Direction.AI_TO_BACKEND,
            keys=KEYS,  # the backend-to-AI secret
            method="POST",
            target="/content/ingestion/callbacks",
            headers=headers,
            body_sha256=sha256_hex(b"{}"),
            now=NOW,
        )


def test_rotation_accepts_the_previous_secret_and_signs_with_the_current() -> None:
    rotated = ServiceKeys(current="new-backend-to-ai-secret-0123456789abcdef!", previous=SECRET)
    # A request signed before the rotation still verifies.
    assert _verify(keys=rotated).request_id == REQUEST_ID
    # New requests carry the current secret's signature.
    headers = sign_request(
        direction=Direction.BACKEND_TO_AI,
        keys=rotated,
        method=METHOD,
        target=TARGET,
        body=BODY,
        context=CONTEXT,
        timestamp=NOW,
        request_id=REQUEST_ID,
    )
    assert headers[HEADER_SIGNATURE] != SIGNATURE
    _verify(headers, keys=ServiceKeys(current=rotated.current))
    # Once the previous secret is dropped, old signatures stop verifying.
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(keys=ServiceKeys(current=rotated.current))


# --- Timestamp --------------------------------------------------------------


@pytest.mark.parametrize("now", [NOW - 60, NOW, NOW + 60])
def test_timestamp_within_the_window_is_accepted(now: int) -> None:
    _verify(now=now)


@pytest.mark.parametrize("now", [NOW - 61, NOW + 61])
def test_timestamp_outside_the_window_is_refused(now: int) -> None:
    with pytest.raises(ServiceAuthError, match="outside window"):
        _verify(now=now)


@pytest.mark.parametrize(
    "value", ["", "01760000000", "-1760000000", "+1760000000", "1760000000.0", "1e9", " 1760000000", "1760000000000"]
)
def test_malformed_timestamp_is_refused(value: str) -> None:
    with pytest.raises(ServiceAuthError, match="malformed timestamp"):
        _verify(_vector_headers(**{HEADER_TIMESTAMP: value}))


# --- Request id ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        REQUEST_ID.upper(),
        REQUEST_ID.replace("-", ""),
        "{" + REQUEST_ID + "}",
        "3f1c0d9e-6b0a-1c55-9d43-1c2b8f7a9e10",  # version 1
        "3f1c0d9e-6b0a-4c55-7d43-1c2b8f7a9e10",  # wrong variant
        "",
    ],
)
def test_request_id_must_be_a_canonical_uuid4(value: str) -> None:
    with pytest.raises(ServiceAuthError, match="UUIDv4"):
        _verify(_vector_headers(**{HEADER_REQUEST_ID: value}))


def test_sign_request_generates_a_fresh_uuid4_per_request() -> None:
    ids = {
        sign_request(
            direction=Direction.BACKEND_TO_AI,
            keys=KEYS,
            method=METHOD,
            target=TARGET,
            body=BODY,
            context=CONTEXT,
            timestamp=NOW,
        )[HEADER_REQUEST_ID]
        for _ in range(3)
    }
    assert len(ids) == 3
    for request_id in ids:
        _verify(
            sign_request(
                direction=Direction.BACKEND_TO_AI,
                keys=KEYS,
                method=METHOD,
                target=TARGET,
                body=BODY,
                context=CONTEXT,
                timestamp=NOW,
                request_id=request_id,
            )
        )


# --- Headers ------------------------------------------------------------------


@pytest.mark.parametrize("missing", SIGNED_HEADERS)
def test_each_missing_header_is_refused(missing: str) -> None:
    headers = _vector_headers()
    del headers[missing]
    with pytest.raises(ServiceAuthError, match="missing headers"):
        _verify(headers)


def test_header_names_are_case_insensitive() -> None:
    _verify({name.lower(): value for name, value in _vector_headers().items()})


class _MultiHeaders:
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def items(self):
        return list(self._items)


def test_a_repeated_signed_header_is_refused() -> None:
    items = list(_vector_headers().items()) + [("x-build-context", CONTEXT_HEADER)]
    with pytest.raises(ServiceAuthError, match="duplicate"):
        _verify(_MultiHeaders(items))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        SIGNATURE.upper(),
        SIGNATURE[3:],
        "v2=" + SIGNATURE[3:],
        SIGNATURE + "0",
        "Bearer " + SECRET,
    ],
)
def test_malformed_signature_header_is_refused(value: str) -> None:
    with pytest.raises(ServiceAuthError, match="malformed signature"):
        _verify(_vector_headers(**{HEADER_SIGNATURE: value}))


# --- Context encoding ---------------------------------------------------------


def test_context_decodes_to_the_signed_bytes() -> None:
    assert decode_context(CONTEXT_HEADER) == (CONTEXT_JSON, CONTEXT)


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        (CONTEXT_HEADER + "=", "unpadded base64url"),
        ("eyJhIjoi++++In0", "unpadded base64url"),  # standard alphabet
        # Same decoded bytes as the vector, differing only in unused bits.
        (CONTEXT_HEADER[:-1] + "1", "not canonical base64url"),
        (CONTEXT_HEADER + "AA", "unpadded base64url"),  # impossible length
        ("not base64!", "unpadded base64url"),
        ("A" * 4097, "too long"),
    ],
    ids=["padded", "std-alphabet", "trailing-bits", "bad-length", "bad-chars", "too-long"],
)
def test_badly_encoded_context_is_refused(header: str, reason: str) -> None:
    with pytest.raises(ServiceAuthError, match=reason):
        decode_context(header)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b'{"a":1, "b":2}', "not canonical JSON"),  # whitespace
        (b'{"b":1,"a":2}', "not canonical JSON"),  # unsorted keys
        (b'{"a":1,"a":1}', "not ASCII JSON"),  # duplicate key
        (b'{"a":NaN}', "not ASCII JSON"),  # non-standard constant
        (b'{"a":"\xc3\xa9"}', "not ASCII JSON"),  # non-ASCII (must be \\u escaped)
        (b"[1,2]", "not a JSON object"),
        (b"null", "not a JSON object"),
        (b"", "not ASCII JSON"),
        (b'{"a":1}\n', "not canonical JSON"),  # trailing newline
    ],
)
def test_non_canonical_context_json_is_refused(raw: bytes, reason: str) -> None:
    with pytest.raises(ServiceAuthError, match=reason):
        decode_context(_b64(raw))


def test_non_ascii_context_values_use_unicode_escapes() -> None:
    raw = canonical_context_bytes({"name": "Adébáyọ̀"})
    assert raw == b'{"name":"Ad\\u00e9b\\u00e1y\\u1ecd\\u0300"}'
    assert decode_context(_b64(raw))[1] == {"name": "Adébáyọ̀"}


def test_a_non_canonical_context_is_refused_even_with_a_valid_signature() -> None:
    raw = b'{"actor": "user"}'
    canonical = canonical_request(
        service=SERVICE,
        method=METHOD,
        target=TARGET,
        timestamp=TIMESTAMP,
        request_id=REQUEST_ID,
        body_sha256=BODY_SHA256,
        context_sha256=sha256_hex(raw),
    )
    headers = _vector_headers(
        **{HEADER_CONTEXT: _b64(raw), HEADER_SIGNATURE: compute_signature(SECRET, canonical)}
    )
    with pytest.raises(ServiceAuthError, match="not canonical JSON"):
        _verify(headers)


# --- Request target and body hash --------------------------------------------


def test_request_target_is_kept_exactly_as_sent() -> None:
    assert request_target(b"/v1/ai/read/a%2Fb", b"q=x%20y&a=1") == "/v1/ai/read/a%2Fb?q=x%20y&a=1"
    assert request_target(b"/v1/ai/chat", b"") == "/v1/ai/chat"


def test_request_target_must_be_ascii() -> None:
    with pytest.raises(ServiceAuthError):
        request_target("/v1/ai/é".encode("utf-8"), b"")


def test_percent_encoding_is_part_of_the_signed_target() -> None:
    headers = sign_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="GET",
        target="/v1/ai/read/a%2Fb",
        body=b"",
        context=CONTEXT,
        timestamp=NOW,
    )
    _verify(headers, method="GET", target="/v1/ai/read/a%2Fb", body=b"")
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        _verify(headers, method="GET", target="/v1/ai/read/a/b", body=b"")


def test_empty_body_hash() -> None:
    assert EMPTY_BODY_SHA256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"") == EMPTY_BODY_SHA256
