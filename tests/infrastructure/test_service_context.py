"""Service context contract (design A.4): strict schema for user and system
contexts, and its enforcement inside signature verification (C10)."""

from typing import Any

import pytest

from app.infrastructure.security.service_context import (
    InvalidServiceContext,
    ServiceContext,
)
from app.infrastructure.security.service_signature import (
    HEADER_CONTEXT,
    HEADER_SIGNATURE,
    Direction,
    ServiceAuthError,
    ServiceKeys,
    canonical_context_bytes,
    canonical_request,
    compute_signature,
    encode_context,
    sha256_hex,
    sign_request,
    verify_request,
)

TENANT = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
USER = "0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d"
MEMBERSHIP = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

USER_CONTEXT: dict[str, Any] = {
    "v": 1,
    "actor": "user",
    "tenant_id": TENANT,
    "user_id": USER,
    "membership_id": MEMBERSHIP,
    "role": "lecturer",
    "permissions": ["ai.questions.generate"],
    "correlation_id": "corr-001",
}
SYSTEM_CONTEXT: dict[str, Any] = {
    "v": 1,
    "actor": "system",
    "tenant_id": TENANT,
    "user_id": None,
    "membership_id": None,
    "role": None,
    "permissions": [],
    "correlation_id": "job-42:attempt-1",
}


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**base, **changes}


# --- valid shapes -------------------------------------------------------------


def test_user_context_round_trips() -> None:
    context = ServiceContext.from_dict(USER_CONTEXT)
    assert context.actor == "user"
    assert context.permissions == ("ai.questions.generate",)
    assert context.to_dict() == USER_CONTEXT


def test_system_context_round_trips() -> None:
    context = ServiceContext.from_dict(SYSTEM_CONTEXT)
    assert (context.user_id, context.membership_id, context.role, context.permissions) == (
        None,
        None,
        None,
        (),
    )
    assert context.to_dict() == SYSTEM_CONTEXT


def test_for_user_records_checked_permissions_sorted_and_unique() -> None:
    context = ServiceContext.for_user(
        tenant_id=TENANT,
        user_id=USER,
        membership_id=MEMBERSHIP,
        role="lecturer",
        permissions=["ai.use", "ai.questions.generate", "ai.use"],
        correlation_id="corr-001",
    )
    assert context.permissions == ("ai.questions.generate", "ai.use")


def test_for_system_has_no_user_and_grants_nothing() -> None:
    context = ServiceContext.for_system(tenant_id=TENANT, correlation_id="job-42:attempt-1")
    assert context.to_dict() == SYSTEM_CONTEXT


def test_vector_context_serialises_to_the_vector_bytes() -> None:
    assert canonical_context_bytes(ServiceContext.from_dict(USER_CONTEXT).to_dict()) == (
        b'{"actor":"user","correlation_id":"corr-001",'
        b'"membership_id":"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",'
        b'"permissions":["ai.questions.generate"],"role":"lecturer",'
        b'"tenant_id":"6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c",'
        b'"user_id":"0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d","v":1}'
    )


# --- refused shapes -------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(USER_CONTEXT))
def test_every_field_is_required(field: str) -> None:
    data = dict(USER_CONTEXT)
    del data[field]
    with pytest.raises(InvalidServiceContext, match="missing"):
        ServiceContext.from_dict(data)


@pytest.mark.parametrize("field", ["tenant", "scope", "is_admin", "V"])
def test_unknown_fields_are_refused(field: str) -> None:
    with pytest.raises(InvalidServiceContext, match="unknown"):
        ServiceContext.from_dict(_with(USER_CONTEXT, **{field: "x"}))


_BAD_USER_VALUES = [
    ("v", 2),
    ("v", "1"),
    ("v", True),
    ("v", 1.0),
    ("v", None),
    ("actor", "admin"),
    ("actor", "User"),
    ("actor", None),
    ("actor", 1),
    ("tenant_id", TENANT.upper()),
    ("tenant_id", TENANT.replace("-", "")),
    ("tenant_id", "{" + TENANT + "}"),
    ("tenant_id", "urn:uuid:" + TENANT),
    ("tenant_id", "tenant-1"),
    ("tenant_id", None),
    ("tenant_id", 7),
    ("user_id", None),
    ("user_id", USER.upper()),
    ("user_id", ""),
    ("membership_id", None),
    ("membership_id", "m-1"),
    ("role", None),
    ("role", ""),
    ("role", ["lecturer"]),
    ("permissions", "ai.use"),
    ("permissions", None),
    ("permissions", {"ai.use": True}),
    ("permissions", ["ai.use", "ai.questions.generate"]),  # unsorted
    ("permissions", ["ai.use", "ai.use"]),  # duplicate
    ("permissions", ["ai.use", 1]),
    ("permissions", [""]),
    ("permissions", [["ai.use"]]),
    ("correlation_id", ""),
    ("correlation_id", "x" * 129),
    ("correlation_id", "has space"),
    ("correlation_id", "slash/not/allowed"),
    ("correlation_id", "line\nbreak"),
    ("correlation_id", 42),
    ("correlation_id", None),
]


@pytest.mark.parametrize(("field", "value"), _BAD_USER_VALUES, ids=[f"{f}={v!r}"[:40] for f, v in _BAD_USER_VALUES])
def test_user_context_with_a_wrong_value_is_refused(field: str, value: Any) -> None:
    with pytest.raises(InvalidServiceContext):
        ServiceContext.from_dict(_with(USER_CONTEXT, **{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", USER),
        ("membership_id", MEMBERSHIP),
        ("role", "admin"),
        ("role", ""),
        ("permissions", ["ai.use"]),
        ("tenant_id", None),
    ],
)
def test_system_context_cannot_carry_a_user_or_permissions(field: str, value: Any) -> None:
    with pytest.raises(InvalidServiceContext):
        ServiceContext.from_dict(_with(SYSTEM_CONTEXT, **{field: value}))


def test_correlation_id_boundaries() -> None:
    for value in ("a", "x" * 128, "A-z.0_9:-"):
        ServiceContext.from_dict(_with(USER_CONTEXT, correlation_id=value))


def test_any_uuid_version_in_canonical_form_is_accepted() -> None:
    v1_style = "6f1c2a7e-4b3d-1c8e-9a1f-2d3e4f5a6b7c"
    assert ServiceContext.from_dict(_with(USER_CONTEXT, tenant_id=v1_style)).tenant_id == v1_style


def test_direct_construction_is_validated_too() -> None:
    with pytest.raises(InvalidServiceContext):
        ServiceContext(actor="system", tenant_id=TENANT, correlation_id="c", role="admin")
    with pytest.raises(InvalidServiceContext):
        ServiceContext.for_user(
            tenant_id=TENANT,
            user_id="not-a-uuid",
            membership_id=MEMBERSHIP,
            role="lecturer",
            permissions=["ai.use"],
            correlation_id="corr-001",
        )


# --- enforced by verification (C10) ---------------------------------------------

SECRET = "test-only-ai-to-backend-secret-fedcba9876543210"
KEYS = ServiceKeys(current=SECRET)
TARGET = "/content/ingestion/callbacks"
BODY = b"{}"
NOW = 1760000000


def _signed_with_raw_context(context: dict[str, Any]) -> dict[str, str]:
    """Sign correctly over an arbitrary decoded context, bypassing the typed
    builder, as a misbehaving sender holding the secret could."""
    headers = sign_request(
        direction=Direction.AI_TO_BACKEND,
        keys=KEYS,
        method="POST",
        target=TARGET,
        body=BODY,
        context=ServiceContext.from_dict(SYSTEM_CONTEXT),
        timestamp=NOW,
    )
    canonical = canonical_request(
        service=Direction.AI_TO_BACKEND.sender,
        method="POST",
        target=TARGET,
        timestamp=str(NOW),
        request_id=headers["X-BUILD-Request-ID"],
        body_sha256=sha256_hex(BODY),
        context_sha256=sha256_hex(canonical_context_bytes(context)),
    )
    headers[HEADER_CONTEXT] = encode_context(context)
    headers[HEADER_SIGNATURE] = compute_signature(SECRET, canonical)
    return headers


def _verify(headers: dict[str, str]):
    return verify_request(
        direction=Direction.AI_TO_BACKEND,
        keys=KEYS,
        method="POST",
        target=TARGET,
        headers=headers,
        body_sha256=sha256_hex(BODY),
        now=NOW,
    )


def test_verification_returns_the_typed_context() -> None:
    verified = _verify(_signed_with_raw_context(SYSTEM_CONTEXT))
    assert verified.context == ServiceContext.from_dict(SYSTEM_CONTEXT)


@pytest.mark.parametrize(
    "context",
    [
        _with(SYSTEM_CONTEXT, extra="x"),
        {k: v for k, v in SYSTEM_CONTEXT.items() if k != "correlation_id"},
        _with(SYSTEM_CONTEXT, v=True),
        _with(SYSTEM_CONTEXT, tenant_id=TENANT.upper()),
        _with(SYSTEM_CONTEXT, permissions=["content.ingest"]),
        _with(USER_CONTEXT, permissions=["b", "a"]),
    ],
    ids=["unknown-field", "missing-field", "bool-version", "upper-uuid", "system-perms", "unsorted"],
)
def test_validly_signed_but_invalid_context_is_refused(context: dict[str, Any]) -> None:
    with pytest.raises(ServiceAuthError, match="invalid context"):
        _verify(_signed_with_raw_context(context))
