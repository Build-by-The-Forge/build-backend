"""Structural rules of the mobile contract (M1). These read the document only:
whether the backend serves it is M2's drift gate, not this test."""

from pathlib import Path
from typing import Any

import pytest
import yaml

SPEC_PATH = Path(__file__).resolve().parents[1] / "contracts" / "mobile" / "openapi.yaml"
METHODS = {"get", "put", "post", "patch", "delete"}
PUBLIC_OPERATIONS = {
    "registerUser",
    "authenticate",
    "refreshSession",
    "verifyEmail",
    "resendVerification",
    "forgotPassword",
    "resetPassword",
}
NOT_TENANT_SCOPED_PREFIXES = ("/identity/", "/tenants/", "/invitations/")
# Names that must never reach a student, wherever they appear in a schema.
FORBIDDEN_PROPERTIES = {
    "storage_uri",
    "storage_key",
    "created_by_email",
    "external_task_id",
    "attempt_history",
    "error_details",
    "chunk_id",
    "correct_option",
    "explanation",
    "context",
    "trust_policy",
}
OUT_OF_SCOPE_PATHS = {
    "/ai/chat",
    "/ai/explain",
    "/ai/memory",
    "/ai/generate-questions",
    "/tenants/{slug}/join-policy",
    "/content/ingestion/callbacks",
}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    ]


def resolve(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in node:
        return node
    found: Any = spec
    for part in node["$ref"].removeprefix("#/").split("/"):
        found = found[part]
    return found


def walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def parameter_names(spec: dict[str, Any], operation: dict[str, Any]) -> set[str]:
    return {resolve(spec, p)["name"] for p in operation.get("parameters", [])}


def json_schema(spec: dict[str, Any], response: dict[str, Any]) -> dict[str, Any] | None:
    content = resolve(spec, response).get("content", {})
    return content.get("application/json", {}).get("schema")


def test_every_reference_resolves(spec):
    for node in walk(spec):
        if "$ref" in node:
            resolve(spec, node)


def test_every_operation_has_a_unique_id(spec):
    ids = [operation["operationId"] for _, _, operation in operations(spec)]
    assert len(ids) == len(set(ids))


def test_every_operation_declares_its_common_failures(spec):
    for path, method, operation in operations(spec):
        responses = operation["responses"]
        assert {"429", "500"} <= set(responses), f"{method} {path}"
        if operation["operationId"] not in PUBLIC_OPERATIONS:
            assert "401" in responses, f"{method} {path}"
        if "requestBody" in operation or {"limit", "offset"} & parameter_names(spec, operation):
            assert "422" in responses, f"{method} {path}"


def test_only_the_public_operations_skip_authentication(spec):
    for path, method, operation in operations(spec):
        public = operation.get("security") == []
        assert public == (operation["operationId"] in PUBLIC_OPERATIONS), f"{method} {path}"


def test_tenant_scoped_operations_require_the_tenant_header(spec):
    for path, method, operation in operations(spec):
        if path.startswith(NOT_TENANT_SCOPED_PREFIXES):
            continue
        assert "X-Tenant-Slug" in parameter_names(spec, operation), f"{method} {path}"
        assert {"400", "403"} <= set(operation["responses"]), f"{method} {path}"


def test_every_failure_uses_the_error_envelope(spec):
    error = {"$ref": "#/components/schemas/ErrorEnvelope"}
    for path, method, operation in operations(spec):
        for status, response in operation["responses"].items():
            if int(status) >= 400:
                assert json_schema(spec, response) == error, f"{method} {path} {status}"


def test_every_json_success_uses_a_success_envelope(spec):
    envelopes = {"#/components/schemas/SuccessEnvelope", "#/components/schemas/PageEnvelope"}
    for path, method, operation in operations(spec):
        for status, response in operation["responses"].items():
            schema = json_schema(spec, response)
            if int(status) < 400 and schema is not None:
                assert schema["allOf"][0]["$ref"] in envelopes, f"{method} {path} {status}"


def test_lists_are_paginated_or_named_as_exceptions(spec):
    assert spec["components"]["parameters"]["Limit"]["schema"]["maximum"] == 100
    for path, method, operation in operations(spec):
        paged = {"limit", "offset"} <= parameter_names(spec, operation)
        schema = json_schema(spec, operation["responses"].get("200", {"content": {}}))
        page_shape = schema is not None and schema.get("allOf", [{}])[0].get("$ref", "").endswith("/PageEnvelope")
        assert paged == page_shape, f"{method} {path}"
        data = (schema or {}).get("allOf", [{}, {}])[-1].get("properties", {}).get("data", {})
        if data.get("type") == "array" and not paged:
            assert operation.get("x-unpaginated") is True, f"{method} {path}"


def test_retried_creations_require_an_idempotency_key(spec):
    required = {"uploadMyDocument", "createConversation", "sendMessage"}
    seen = {
        operation["operationId"] for _, _, operation in operations(spec) if "Idempotency-Key" in parameter_names(spec, operation)
    }
    assert seen == required


def test_internals_never_appear_in_a_schema(spec):
    for node in walk(spec["components"]["schemas"]):
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert not FORBIDDEN_PROPERTIES & set(properties)


def test_grading_appears_only_in_a_submitted_result(spec):
    holders = [name for name, schema in spec["components"]["schemas"].items() if "is_correct" in schema.get("properties", {})]
    assert holders == ["QuestionResult"]


def test_an_assessment_carries_no_questions(spec):
    assert "questions" not in spec["components"]["schemas"]["Assessment"]["properties"]


def test_an_assessment_states_its_attempt_policy(spec):
    assert "attempt_policy" in spec["components"]["schemas"]["Assessment"]["required"]


def test_feedback_can_be_withheld_from_a_result(spec):
    properties = spec["components"]["schemas"]["QuestionResult"]["properties"]
    assert "null" in properties["is_correct"]["type"]
    assert "null" in properties["awarded_marks"]["type"]


def test_access_and_knowledge_scope_are_separate_fields(spec):
    document = spec["components"]["schemas"]["Document"]
    assert {"ownership", "knowledge_scope"} <= set(document["required"])


def test_a_citation_has_exactly_the_approved_fields(spec):
    citation = spec["components"]["schemas"]["Citation"]
    expected = {"number", "source_id", "asset_id", "title", "page_start", "page_end", "excerpt"}
    assert set(citation["properties"]) == expected
    assert citation["additionalProperties"] is False


def test_the_contract_stays_student_only(spec):
    assert not OUT_OF_SCOPE_PATHS & set(spec["paths"])
    for path, _, _ in operations(spec):
        assert "/publish" not in path and "/archive" not in path and "/dispatch" not in path


def test_every_error_code_named_in_a_description_is_registered(spec):
    registered = set(spec["components"]["schemas"]["ErrorCode"]["enum"])
    described = set()
    responses = [r for _, _, op in operations(spec) for r in op["responses"].values() if "$ref" not in r]
    responses += list(spec["components"]["responses"].values())
    for response in responses:
        described |= {
            word.strip(".,:") for word in response["description"].split() if word.strip(".,:").isupper() and "_" in word
        }
    assert described
    assert described <= registered
